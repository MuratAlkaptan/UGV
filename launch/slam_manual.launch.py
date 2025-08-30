from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    slam_params = LaunchConfiguration("slam_params_file")
    use_sim_time = LaunchConfiguration("use_sim_time")

    return LaunchDescription([
        DeclareLaunchArgument(
            "slam_params_file",
            default_value=os.path.join(
                get_package_share_directory("sam_bot_description"),
                "config",
                "mapper_params_online_async.yaml"),
            description="Full path to the slam_toolbox params file"),
        DeclareLaunchArgument("use_sim_time", default_value="true"),

        Node(
            package="slam_toolbox",
            executable="async_slam_toolbox_node",
            name="slam_toolbox",
            output="screen",
            parameters=[slam_params, {"use_sim_time": use_sim_time}],
        ),

        Node(
            package="teleop_twist_keyboard",
            executable="teleop_twist_keyboard",
            name="teleop",
            output="screen",
            prefix="xterm -e",  # open in a new terminal tab
        )
    ])
