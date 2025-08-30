from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    map_file = LaunchConfiguration("map")
    params_file = LaunchConfiguration("params_file")

    default_params = os.path.join(
        get_package_share_directory("nav2_bringup"), "params", "nav2_params.yaml"
    )

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("map", description="Full path to map yaml file"),
        DeclareLaunchArgument("params_file", default_value=default_params),

        Node(
            package="nav2_bringup",
            executable="bringup_launch.py",
            output="screen",
            parameters=[{"use_sim_time": use_sim_time}],
            arguments=["map:=" + map_file, "params_file:=" + params_file]
        )
    ])
