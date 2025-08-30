from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import Command, LaunchConfiguration
import os
from launch_ros.actions import Node

def generate_launch_description():
    pkg_share = FindPackageShare(package='sam_bot_description').find('sam_bot_description')
    default_model_path = os.path.join(pkg_share, 'src', 'description', 'robot.urdf.xacro')

    # Robot state publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': Command(['xacro ', LaunchConfiguration('model')])}]
    )

    # Joint state publisher node
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        arguments=[default_model_path],  # Add this line
    )

    # spawner for diff drive controller
    diff_drive_spawner = Node(
    package="controller_manager",
    executable="spawner",
    arguments=["diff_cont", "-c", "/controller_manager"],
    output="screen"
)

    # spawner for joint state broadcaster
    joint_broad_spawner = Node(
        package="controller_manager",
        executable="spawner",
        arguments=["joint_broad"],
        output="screen"
    )

    robot_localization_node = Node(
    package='robot_localization',
    executable='ekf_node',
    name='ekf_node',
    output='screen',
    parameters=[os.path.join(pkg_share, 'config/ekf.yaml'), {'use_sim_time': LaunchConfiguration('use_sim_time')}]
    )
    
    return LaunchDescription([
    Node(
        package="topic_tools",
        executable="relay",
        name="cmd_vel_relay",
        arguments=["/cmd_vel", "/diff_cont/cmd_vel_unstamped"]
    ),
    DeclareLaunchArgument(name='use_sim_time', default_value='True',description='Flag to enable use_sim_time'),
    DeclareLaunchArgument(name='model', default_value=default_model_path, description='Absolute path to robot model file'),
    joint_state_publisher_node,
    robot_state_publisher_node,
    robot_localization_node,
    diff_drive_spawner,
    joint_broad_spawner
    ])

