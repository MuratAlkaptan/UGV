from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    slam_params = LaunchConfiguration("slam_params_file")
    use_sim_time = LaunchConfiguration("use_sim_time")
# Path to joystick config
    joy_params = os.path.join(
        get_package_share_directory('rovalp'),
        'config',
        'joystick.yaml'
    )
    return LaunchDescription([
        DeclareLaunchArgument(
            "slam_params_file",
            default_value=os.path.join(
                get_package_share_directory("rovalp"),
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

    # joystick + teleop nodes
    Node(
        package='joy',
        executable='joy_node',
        parameters=[joy_params, {'use_sim_time': use_sim_time}],
    ),

    Node(
        package='teleop_twist_joy',
        executable='teleop_node',
        name='teleop_node',
        parameters=[joy_params, {'use_sim_time': use_sim_time}],
        remappings=[('/cmd_vel', '/diff_cont/cmd_vel_unstamped')]
    ),
    Node(
            package='rplidar_ros',
            executable='rplidar_composition',
            output='screen',
            parameters=[{
                'serial_port': '/dev/ttyUSB0',  # adjust
                'frame_id': 'laser_link',
                'angle_compensate': True,
                'scan_mode': 'Standard'
            }]
        ),
    ])
