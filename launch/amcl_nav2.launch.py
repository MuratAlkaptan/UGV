from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    use_sim_time = LaunchConfiguration("use_sim_time")
    map_file     = LaunchConfiguration("map")
    params_file  = LaunchConfiguration("params_file")

    # defaults inside *your* package (make sure these files exist)
    pkg_share = get_package_share_directory("sam_bot_description")
    default_map = os.path.join(pkg_share, "maps", "my_map_save.yaml")
    default_params = os.path.join(pkg_share, "params", "rovalp_nav2_params.yaml")

    nav2_bringup_dir = get_package_share_directory("nav2_bringup")
    bringup_launch   = os.path.join(nav2_bringup_dir, "launch", "bringup_launch.py")

    return LaunchDescription([
        DeclareLaunchArgument("use_sim_time", default_value="true"),
        DeclareLaunchArgument("map",          default_value=default_map,
                              description="Full path to map yaml file"),
        DeclareLaunchArgument("params_file",  default_value=default_params),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(bringup_launch),
            launch_arguments={
                "use_sim_time": use_sim_time,
                "map":          map_file,
                "params_file":  params_file,
            }.items(),
        ),
    ])
