from launch import LaunchDescription
from launch.actions import IncludeLaunchDescription, ExecuteProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource, AnyLaunchDescriptionSource
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    ld = LaunchDescription()

    # === Paths ===
    sam_pkg = get_package_share_directory('sam_bot_description')
    slam_params = os.path.join(sam_pkg, 'config', 'mapper_params_online_async.yaml')
    twist_mux_config = os.path.join(sam_pkg, 'config', 'twist_mux.yaml')

    # === SLAM Toolbox ===
    slam_toolbox = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('slam_toolbox'), 'launch', 'online_async_launch.py')
        ),
        launch_arguments={
            'slam_params_file': slam_params,
            'use_sim_time': 'true'
        }.items()
    )

    # === Robot + RViz (display) ===
    display = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sam_pkg, 'launch', 'display.launch.py')
        )
    )

    # === Nav2 Bringup ===
    nav2 = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(get_package_share_directory('nav2_bringup'), 'launch', 'navigation_launch.py')
        ),
        launch_arguments={'use_sim_time': 'true'}.items()
    )

    # === Joystick Teleop ===
    joystick = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(sam_pkg, 'launch', 'joystick.launch.py')
        )
    )

    # === Rosbridge ===
    rosbridge = IncludeLaunchDescription(
        AnyLaunchDescriptionSource(
            os.path.join(get_package_share_directory('rosbridge_server'), 'launch', 'rosbridge_websocket_launch.xml')
        )
    )

    # === Websocket FastAPI Bridge ===
    websocket_bridge = ExecuteProcess(
        cmd=['python3', os.path.join(sam_pkg, 'script', 'ros2_fastapi_websocket_bridge.py')],
        output='screen'
    )

    # === Twist Mux ===
    twist_mux = Node(
        package="twist_mux",
        executable="twist_mux",
        name="twist_mux",
        output="screen",
        parameters=["/home/sam/colcon_ws/src/sam_bot_description/config/twist_mux.yaml"],
        remappings=[
            ("cmd_vel_out", "diff_cont/cmd_vel_unstamped"),
        ],
    )

    # Add everything to LaunchDescription
    ld.add_action(slam_toolbox)
    ld.add_action(display)
    ld.add_action(nav2)
    ld.add_action(joystick)
    ld.add_action(rosbridge)
    ld.add_action(websocket_bridge)
    ld.add_action(twist_mux)

    return ld
