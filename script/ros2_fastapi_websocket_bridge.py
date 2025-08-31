import json
import rclpy
from rclpy.node import Node
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from geometry_msgs.msg import Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from slam_toolbox.srv import SerializePoseGraph

app = FastAPI()

# Open every CORS origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

rclpy.init()

class BridgeNode(Node):
    def __init__(self):
        super().__init__("websocket_bridge")

        # Publisher for teleop
        self.teleop_pub = self.create_publisher(Twist, "/diff_cont/cmd_vel_unstamped", 10)

        # Nav2 action client
        self.nav_to_pose_client = ActionClient(self, NavigateToPose, "navigate_to_pose")

        # Slam Toolbox serialize service
        self.serialize_cli = self.create_client(SerializePoseGraph, "/slam_toolbox/serialize_map")

    async def handle_message(self, msg: str):
        data = json.loads(msg)

        if data["type"] == "teleop":
            twist = Twist()
            twist.linear.x = float(data.get("linear", 0.0))
            twist.angular.z = float(data.get("angular", 0.0))
            self.teleop_pub.publish(twist)

        elif data["type"] == "goal":
            if not self.nav_to_pose_client.wait_for_server(timeout_sec=2.0):
                self.get_logger().error("Nav2 action server not available")
                return
            goal_msg = NavigateToPose.Goal()
            goal_msg.pose.header.frame_id = "map"
            goal_msg.pose.header.stamp = self.get_clock().now().to_msg()
            goal_msg.pose.pose.position.x = float(data["x"])
            goal_msg.pose.pose.position.y = float(data["y"])
            # yaw -> quaternion
            import math
            from geometry_msgs.msg import Quaternion
            q = Quaternion()
            q.z = math.sin(float(data["yaw"]) / 2.0)
            q.w = math.cos(float(data["yaw"]) / 2.0)
            goal_msg.pose.pose.orientation = q
            self.nav_to_pose_client.send_goal_async(goal_msg)

        elif data["type"] == "save_map":
            filename = data.get("name", "my_serialized_map")
            full_path = f"/home/sam/ws/maps/{filename}"
            if not self.serialize_cli.wait_for_service(timeout_sec=2.0):
                self.get_logger().error("Serialize service not available")
                return
            req = SerializePoseGraph.Request()
            req.filename = full_path
            self.get_logger().info(f"Saving serialized map to {full_path}")
            future = self.serialize_cli.call_async(req)
            rclpy.spin_until_future_complete(self, future)
            if future.result() is not None:
                self.get_logger().info("Map serialized successfully")
            else:
                self.get_logger().error("Failed to serialize map")

node = BridgeNode()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        try:
            data = await websocket.receive_text()
            await node.handle_message(data)
        except Exception as e:
            print(f"WebSocket error: {e}")
            break

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
