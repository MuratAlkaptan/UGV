#!/usr/bin/env python3
"""
ROS ​2 (Humble) ↔ FastAPI WebSocket bridge for real robot + simulation.

Features
- FastAPI WebSocket server (ws://<host>:8000/ws) that:
  • broadcasts robot state (pose, odom, LaserScan, Nav2 events)
  • streams map metadata on change and can send map files upon request
  • receives manual drive commands and publishes to diff_drive_controller
  • receives Nav2 NavigateToPose goals and relays feedback/results
  • lets UI switch modes (manual / mapping / nav2) and trigger map save

Design notes
- rclpy runs in a background thread with a MultiThreadedExecutor.
- ROS callbacks push lightweight JSON dicts into an asyncio.Queue.
- A ConnectionManager fan-outs messages to all connected clients.
- Heuristics to detect "unmapped area" using AMCL covariance and map cells.
- Rate limiting on heavy topics (scan, map) to keep bandwidth sane.

Tested targets (intended): Ubuntu 22.04, ROS ​2 Humble, Python 3.10.

Author: Murat Alkaptan
License: MIT
"""

from __future__ import annotations
import asyncio
import base64
import json
import math
import os
import threading
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Dict, List, Optional, Set
import signal

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import rclpy
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from rclpy.callback_groups import ReentrantCallbackGroup

from geometry_msgs.msg import Twist, PoseWithCovarianceStamped
from nav_msgs.msg import Odometry, OccupancyGrid
from sensor_msgs.msg import LaserScan

from rclpy.action import ActionClient
from nav2_msgs.action import NavigateToPose

# Optional: map saver service (Nav2)
try:
    from nav2_msgs.srv import SaveMap
except Exception:  # pragma: no cover
    SaveMap = None  # type: ignore

# -----------------------------
# Configuration (edit as needed)
# -----------------------------
CMD_VEL_TOPIC = os.environ.get("CMD_VEL_TOPIC", "/diff_cont/cmd_vel_unstamped")
ODOM_TOPIC = os.environ.get("ODOM_TOPIC", "/odom")
AMCL_POSE_TOPIC = os.environ.get("AMCL_POSE_TOPIC", "/amcl_pose")
LASER_TOPIC = os.environ.get("LASER_TOPIC", "/scan")
MAP_TOPIC = os.environ.get("MAP_TOPIC", "/map")

NAV2_ACTION_NAME = os.environ.get("NAV2_ACTION_NAME", "navigate_to_pose")

# Publish rates to the WebSocket (Hz)
POSE_HZ = float(os.environ.get("POSE_HZ", 10))
ODOM_HZ = float(os.environ.get("ODOM_HZ", 10))
SCAN_HZ = float(os.environ.get("SCAN_HZ", 2))  # keep this modest
MAP_PUSH_ON_CHANGE = True  # push map metadata when header stamp changes

# Heuristic thresholds
AMCL_COV_THRESHOLD = float(os.environ.get("AMCL_COV_THRESHOLD", 0.5))  # if cov yaw>thr, flag as uncertain

# Max ranges items sent to UI per scan (downsample to reduce payload)
SCAN_DECIMATE = int(os.environ.get("SCAN_DECIMATE", 4))

# -----------------------------
# WebSocket connection manager
# -----------------------------
class ConnectionManager:
    def __init__(self):
        self.active: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        async with self._lock:
            self.active.add(websocket)

    async def disconnect(self, websocket: WebSocket):
        async with self._lock:
            if websocket in self.active:
                self.active.remove(websocket)

    async def broadcast(self, message: Dict):
        if not self.active:
            return
        data = json.dumps(message, separators=(",", ":"))
        dead: List[WebSocket] = []
        for ws in list(self.active):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.disconnect(ws)


manager = ConnectionManager()

# -----------------------------
# ROS Node
# -----------------------------
class BridgeNode(Node):
    def __init__(self):
        super().__init__("ws_bridge")
        self.cb_group = ReentrantCallbackGroup()
        qos_best_effort = QoSProfile(reliability=ReliabilityPolicy.BEST_EFFORT,
                                     history=HistoryPolicy.KEEP_LAST, depth=5)
        qos_reliable = QoSProfile(reliability=ReliabilityPolicy.RELIABLE,
                                  history=HistoryPolicy.KEEP_LAST, depth=10)

        # Publishers
        self.cmd_pub = self.create_publisher(Twist, CMD_VEL_TOPIC, 10)

        # Subscriptions
        self.odom_msg: Optional[Odometry] = None
        self.amcl_msg: Optional[PoseWithCovarianceStamped] = None
        self.map_msg: Optional[OccupancyGrid] = None
        self._map_stamp: Optional[int] = None

        self.create_subscription(Odometry, ODOM_TOPIC, self._on_odom, qos_reliable, callback_group=self.cb_group)
        self.create_subscription(PoseWithCovarianceStamped, AMCL_POSE_TOPIC, self._on_amcl, qos_reliable, callback_group=self.cb_group)
        self.create_subscription(OccupancyGrid, MAP_TOPIC, self._on_map, qos_reliable, callback_group=self.cb_group)
        self.create_subscription(LaserScan, LASER_TOPIC, self._on_scan, qos_best_effort, callback_group=self.cb_group)

        # Nav2 Action Client
        self.nav_client = ActionClient(self, NavigateToPose, NAV2_ACTION_NAME, callback_group=self.cb_group)
        self._nav_goal_handle = None

        # Async queues into the WS layer
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=100)

        # Rate timers
        self._pose_last_pub = 0.0
        self._odom_last_pub = 0.0
        self._scan_last_pub = 0.0

        # Periodic timers to push state even if callbacks are quiet
        self.create_timer(1.0 / max(POSE_HZ, 0.1), self._tick_pose, callback_group=self.cb_group)
        self.create_timer(1.0 / max(ODOM_HZ, 0.1), self._tick_odom, callback_group=self.cb_group)

    # ------------------ ROS Callbacks ------------------
    def _on_odom(self, msg: Odometry):
        self.odom_msg = msg
        now = time.time()
        if now - self._odom_last_pub >= 1.0 / max(ODOM_HZ, 0.1):
            self._odom_last_pub = now
            asyncio.run_coroutine_threadsafe(self.queue.put(self._fmt_odom(msg)), asyncio.get_event_loop())

    def _on_amcl(self, msg: PoseWithCovarianceStamped):
        self.amcl_msg = msg
        # Detect high uncertainty → request manual mode
        cov = msg.pose.covariance
        yaw_cov = cov[35] if len(cov) >= 36 else 999.0
        if yaw_cov > AMCL_COV_THRESHOLD:
            alert = {
                "type": "unmapped_area",
                "reason": "amcl_covariance_high",
                "yaw_cov": yaw_cov,
                "threshold": AMCL_COV_THRESHOLD,
                "stamp": self._stamp_to_float(msg.header.stamp),
            }
            asyncio.run_coroutine_threadsafe(self.queue.put(alert), asyncio.get_event_loop())

    def _on_map(self, msg: OccupancyGrid):
        self.map_msg = msg
        stamp_int = msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
        if MAP_PUSH_ON_CHANGE and stamp_int != self._map_stamp:
            self._map_stamp = stamp_int
            asyncio.run_coroutine_threadsafe(self.queue.put(self._fmt_map_meta(msg)), asyncio.get_event_loop())

    def _on_scan(self, msg: LaserScan):
        now = time.time()
        if now - self._scan_last_pub < 1.0 / max(SCAN_HZ, 0.1):
            return
        self._scan_last_pub = now
        # Decimate ranges
        ranges = msg.ranges[::SCAN_DECIMATE] if SCAN_DECIMATE > 1 else list(msg.ranges)
        data = {
            "type": "scan",
            "stamp": self._stamp_to_float(msg.header.stamp),
            "angle_min": msg.angle_min,
            "angle_max": msg.angle_max,
            "angle_increment": msg.angle_increment * (SCAN_DECIMATE if SCAN_DECIMATE > 1 else 1),
            "range_min": msg.range_min,
            "range_max": msg.range_max,
            "ranges": ranges,
        }
        asyncio.run_coroutine_threadsafe(self.queue.put(data), asyncio.get_event_loop())

    # ------------------ Formatters ------------------
    def _fmt_pose(self, msg: PoseWithCovarianceStamped) -> Dict:
        x = msg.pose.pose.position.x
        y = msg.pose.pose.position.y
        # yaw from quaternion
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w*q.z + q.x*q.y), 1.0 - 2.0*(q.y*q.y + q.z*q.z))
        return {
            "type": "pose",
            "frame": msg.header.frame_id,
            "x": x,
            "y": y,
            "yaw": yaw,
            "cov": list(msg.pose.covariance),
            "stamp": self._stamp_to_float(msg.header.stamp),
        }

    def _fmt_odom(self, msg: Odometry) -> Dict:
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        yaw = math.atan2(2.0 * (q.w*q.z + q.x*q.y), 1.0 - 2.0*(q.y*q.y + q.z*q.z))
        return {
            "type": "odom",
            "frame": msg.header.frame_id,
            "child_frame": msg.child_frame_id,
            "x": p.x,
            "y": p.y,
            "yaw": yaw,
            "linear": {
                "x": msg.twist.twist.linear.x,
                "y": msg.twist.twist.linear.y,
            },
            "angular": {"z": msg.twist.twist.angular.z},
            "stamp": self._stamp_to_float(msg.header.stamp),
        }

    def _fmt_map_meta(self, msg: OccupancyGrid) -> Dict:
        info = msg.info
        return {
            "type": "map_meta",
            "resolution": info.resolution,
            "width": info.width,
            "height": info.height,
            "origin": {
                "x": info.origin.position.x,
                "y": info.origin.position.y,
            },
            "stamp": self._stamp_to_float(msg.header.stamp),
        }

    def _stamp_to_float(self, stamp) -> float:
        return float(stamp.sec) + float(stamp.nanosec) * 1e-9

    # ------------------ Periodic ticks ------------------
    def _tick_pose(self):
        if self.amcl_msg is not None:
            asyncio.run_coroutine_threadsafe(self.queue.put(self._fmt_pose(self.amcl_msg)), asyncio.get_event_loop())

    def _tick_odom(self):
        if self.odom_msg is not None:
            asyncio.run_coroutine_threadsafe(self.queue.put(self._fmt_odom(self.odom_msg)), asyncio.get_event_loop())

    # ------------------ Robot control ------------------
    def publish_cmd(self, vx: float, vy: float, omega: float):
        msg = Twist()
        msg.linear.x = float(vx)
        msg.linear.y = float(vy)
        msg.angular.z = float(omega)
        self.cmd_pub.publish(msg)

    # ------------------ Nav2 actions ------------------
    async def send_nav_goal(self, x: float, y: float, yaw: float) -> bool:
        # Ensure server available
        if not self.nav_client.wait_for_server(timeout_sec=1.0):
            await self.queue.put({"type": "nav2_event", "event": "server_unavailable"})
            return False
        goal_msg = NavigateToPose.Goal()
        # Fill pose in map frame
        from geometry_msgs.msg import PoseStamped, Quaternion
        goal_msg.pose = PoseStamped()
        goal_msg.pose.header.frame_id = "map"
        goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
        goal_msg.pose.pose.position.x = x
        goal_msg.pose.pose.position.y = y
        # convert yaw to quaternion
        half = yaw / 2.0
        goal_msg.pose.pose.orientation.w = math.cos(half)
        goal_msg.pose.pose.orientation.z = math.sin(half)

        await self.queue.put({"type": "nav2_event", "event": "goal_sent", "x": x, "y": y, "yaw": yaw})

        send_future = self.nav_client.send_goal_async(goal_msg, feedback_callback=self._on_nav_feedback)
        goal_handle = await asyncio.wrap_future(asyncio.get_running_loop().run_in_executor(None, send_future.result))
        if not goal_handle.accepted:
            await self.queue.put({"type": "nav2_event", "event": "rejected"})
            return False
        self._nav_goal_handle = goal_handle
        result_future = goal_handle.get_result_async()
        result = await asyncio.wrap_future(asyncio.get_running_loop().run_in_executor(None, result_future.result))
        status = int(result.status)
        await self.queue.put({"type": "nav2_event", "event": "result", "status": status})
        return True

    def _on_nav_feedback(self, feedback_msg):
        fb = feedback_msg.feedback
        try:
            pose = fb.current_pose.pose.pose
            data = {
                "type": "nav2_event",
                "event": "feedback",
                "distance_remaining": getattr(fb, "distance_remaining", None),
                "speed": getattr(fb, "speed", None),
                "x": pose.position.x,
                "y": pose.position.y,
            }
        except Exception:
            data = {"type": "nav2_event", "event": "feedback"}
        asyncio.run_coroutine_threadsafe(self.queue.put(data), asyncio.get_event_loop())

    async def cancel_nav(self):
        if self._nav_goal_handle is None:
            await self.queue.put({"type": "nav2_event", "event": "no_active_goal"})
            return False
        cancel_future = self._nav_goal_handle.cancel_goal_async()
        result = await asyncio.wrap_future(asyncio.get_running_loop().run_in_executor(None, cancel_future.result))
        await self.queue.put({"type": "nav2_event", "event": "canceled", "return_code": str(result.return_code)})
        self._nav_goal_handle = None
        return True

    # ------------------ Map save ------------------
    async def save_map(self, name: str = "map"):  # returns dict with file paths
        if SaveMap is None:
            return {"ok": False, "error": "SaveMap service not available in env"}
        cli = self.create_client(SaveMap, "save_map")  # typical name; adjust if different
        if not cli.wait_for_service(timeout_sec=2.0):
            return {"ok": False, "error": "save_map service unavailable"}
        req = SaveMap.Request()
        req.map_url = name
        req.image_format = "pgm"
        req.free_thresh = 0.25
        req.occupied_thresh = 0.65
        fut = cli.call_async(req)
        result = await asyncio.wrap_future(asyncio.get_running_loop().run_in_executor(None, fut.result))
        return {"ok": True, "result": str(result)}


# -----------------------------
# Spin rclpy in background thread
# -----------------------------
@dataclass
class RosRuntime:
    node: Optional[BridgeNode] = None
    executor: Optional[MultiThreadedExecutor] = None
    thread: Optional[threading.Thread] = None

    def start(self):
        if self.node:
            return
        rclpy.init(args=None)
        self.node = BridgeNode()
        self.executor = MultiThreadedExecutor()
        self.executor.add_node(self.node)
        self.thread = threading.Thread(target=self.executor.spin, daemon=True)
        self.thread.start()

    def stop(self):
        if self.executor:
            self.executor.shutdown()
        if self.node:
            self.node.destroy_node()
        rclpy.shutdown()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)


rosrt = RosRuntime()

# -----------------------------
# FastAPI App
# -----------------------------
app = FastAPI(title="ROS2 FastAPI WebSocket Bridge", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def _on_startup():
    rosrt.start()
    # Start the fanout task
    asyncio.create_task(_broadcast_loop())


@app.on_event("shutdown")
async def _on_shutdown():
    rosrt.stop()


@app.get("/health")
async def health():
    return JSONResponse({"ok": True})


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        # greet
        await ws.send_text(json.dumps({
            "type": "hello",
            "cmd_vel_topic": CMD_VEL_TOPIC,
            "odom_topic": ODOM_TOPIC,
            "amcl_topic": AMCL_POSE_TOPIC,
            "scan_topic": LASER_TOPIC,
            "map_topic": MAP_TOPIC,
        }))
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                await ws.send_text(json.dumps({"type": "error", "error": "bad_json"}))
                continue
            await _handle_incoming(msg)
    except WebSocketDisconnect:
        await manager.disconnect(ws)
    except Exception as e:  # pragma: no cover
        await manager.disconnect(ws)


# -----------------------------
# Broadcast loop: forward ROS queue to all clients
# -----------------------------
async def _broadcast_loop():
    node = rosrt.node
    assert node is not None
    while True:
        msg = await node.queue.get()
        await manager.broadcast(msg)


# Track subprocess launched for modes
current_process: Optional[asyncio.subprocess.Process] = None
current_mode: Optional[str] = None

async def _stream_process_output(proc: asyncio.subprocess.Process, mode_name: str):
    # read stdout and stderr and broadcast lines
    try:
        if proc.stdout is not None:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                await manager.broadcast({"type": "mode_log", "mode": mode_name, "stream": "stdout", "line": line.decode(errors='ignore').rstrip()})
        if proc.stderr is not None:
            while True:
                line = await proc.stderr.readline()
                if not line:
                    break
                await manager.broadcast({"type": "mode_log", "mode": mode_name, "stream": "stderr", "line": line.decode(errors='ignore').rstrip()})
    except Exception:
        pass

async def handle_mode_command(command: str):
    """Start/stop launch files for modes (slam_manual, amcl_nav2).

    This uses asyncio.create_subprocess_exec so it won't block the FastAPI event loop.
    """
    global current_process, current_mode
    # Stop previous if running
    if current_process is not None:
        try:
            if current_process.returncode is None:
                await manager.broadcast({"type": "mode", "event": "stopping", "mode": current_mode})
                try:
                    current_process.send_signal(signal.SIGINT)
                    await asyncio.wait_for(current_process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    try:
                        current_process.terminate()
                        await asyncio.wait_for(current_process.wait(), timeout=2.0)
                    except asyncio.TimeoutError:
                        current_process.kill()
                        await current_process.wait()
        except Exception:
            pass
        current_process = None
        current_mode = None

    # Launch requested mode
    if command == "slam_manual":
        cmd = ["ros2", "launch", "sam_bot_description", "slam_manual.launch.py"]
    elif command == "amcl_nav2":
        cmd = ["ros2", "launch", "sam_bot_description", "amcl_nav2.launch.py"]
    elif command == "stop":
        await manager.broadcast({"type": "mode", "event": "stopped", "mode": None})
        return
    else:
        await manager.broadcast({"type": "mode", "event": "unknown", "mode": command})
        return

    await manager.broadcast({"type": "mode", "event": "starting", "mode": command, "cmd": cmd})
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        current_process = proc
        current_mode = command
        await manager.broadcast({"type": "mode", "event": "started", "mode": command, "pid": proc.pid})
        # spawn background reader to stream logs back to clients
        asyncio.create_task(_stream_process_output(proc, command))
    except Exception as e:
        await manager.broadcast({"type": "mode", "event": "failed", "mode": command, "error": str(e)})


# -----------------------------
# Incoming message handler (UI → Robot)
# -----------------------------
async def _handle_incoming(msg: Dict):
    node = rosrt.node
    assert node is not None
    mtype = msg.get("type")

    # Mode switching
    if mtype == "mode":
        # Accept either {"type":"mode","mode":"slam_manual"} or {"type":"mode","payload":{"name":"slam_manual"}}
        mode = msg.get("mode") or (msg.get("payload") or {}).get("name")
        if not mode:
            await manager.broadcast({"type": "mode", "event": "error", "error": "no_mode_specified"})
            return
        asyncio.create_task(handle_mode_command(mode))
        await manager.broadcast({"type": "mode", "event": "requested", "mode": mode})
        return

    if mtype == "drive":
        vx = float(msg.get("vx", 0.0))
        vy = float(msg.get("vy", 0.0))
        omega = float(msg.get("omega", 0.0))
        node.publish_cmd(vx, vy, omega)
        return

    if mtype == "nav2_goal":
        x = float(msg.get("x", 0.0))
        y = float(msg.get("y", 0.0))
        yaw = float(msg.get("yaw", 0.0))
        asyncio.create_task(node.send_nav_goal(x, y, yaw))
        return

    if mtype == "nav2_cancel":
        asyncio.create_task(node.cancel_nav())
        return

    if mtype == "save_map":
        name = str(msg.get("name", "map"))
        result = await node.save_map(name)
        await manager.broadcast({"type": "save_map_result", **result})
        return

    if mtype == "request_map_file":
        # Generate a PGM + YAML payload from last map_msg
        pm = node.map_msg
        if pm is None:
            await manager.broadcast({"type": "map_file", "ok": False, "error": "no_map"})
            return
        pgm_bytes, yaml_text = _occupancy_to_pgm_yaml(pm)
        await manager.broadcast({
            "type": "map_file",
            "ok": True,
            "pgm_b64": base64.b64encode(pgm_bytes).decode("ascii"),
            "yaml": yaml_text,
        })
        return

    # Unknown
    await manager.broadcast({"type": "warn", "msg": f"unknown_type:{mtype}"})


# -----------------------------
# Utility: Convert OccupancyGrid → PGM+YAML (like map_saver)
# -----------------------------

def _occupancy_to_pgm_yaml(grid: OccupancyGrid) -> (bytes, str):
    import numpy as np
    w = grid.info.width
    h = grid.info.height
    data = np.array(grid.data, dtype=np.int16).reshape(h, w)
    # Map to [0..255] per ROS conventions: -1=unknown(205), 0=free(254), 100=occ(0)
    img = np.full((h, w), 205, dtype=np.uint8)  # unknown
    img[data == 0] = 254
    img[data == 100] = 0
    # flip vertically to match ROS map_saver output
    img = np.flipud(img)

    # write binary PGM
    bio = BytesIO()
    header = f"P5{w} {h}255".encode("ascii")
    bio.write(header)
    bio.write(img.tobytes())
    pgm_bytes = bio.getvalue()

    # YAML content
    res = grid.info.resolution
    ox = grid.info.origin.position.x
    oy = grid.info.origin.position.y
    yaml_text = (
        "image: map.pgm"
        f"resolution: {res}"
        f"origin: [{ox}, {oy}, 0.0]"
        "negate: 0 occupied_thresh: 0.65 free_thresh: 0.25"
    )
    return pgm_bytes, yaml_text


# -----------------------------
# Entrypoint
# -----------------------------
if __name__ == "__main__":
    # Run with: python3 ros2_fastapi_websocket_bridge.py
    # Or: uvicorn ros2_fastapi_websocket_bridge:app --host 0.0.0.0 --port 8000
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")