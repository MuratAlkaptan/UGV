# launch/ros2_control_launch.py
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('rovalp')
    default_model_path = os.path.join(pkg_share, 'src', 'description', 'robot.urdf.xacro')
    controllers_file = os.path.join(pkg_share, 'config', 'controllers.yaml')
    ekf_file = os.path.join(pkg_share, 'config', 'ekf.yaml')

    # Node: robot_state_publisher
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': Command(['xacro ', LaunchConfiguration('model')])}],
        output='screen'
    )

    # Node: joint_state_publisher (optional argument file)
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        arguments=[default_model_path],
        output='screen'
    )

    # ros2_control (controller_manager) node - start first
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[
            controllers_file,  # controller config file
            {'robot_description': Command(['xacro ', LaunchConfiguration('model')])}
        ],
        output="screen"
    )

    # Spawners: delayed slightly to avoid race on controller_manager startup
    spawn_joint_state_broadcaster = TimerAction(
        period=2.0,
        actions=[
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["joint_state_broadcaster", "-c", "/controller_manager"],
                output="screen"
            )
        ]
    )

    spawn_diff_cont = TimerAction(
        period=2.5,
        actions=[
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=["diff_cont", "-c", "/controller_manager"],
                output="screen"
            )
        ]
    )

    # topic relay (cmd_vel -> diff_cont/cmd_vel_unstamped)
    cmd_vel_relay = Node(
        package="topic_tools",
        executable="relay",
        name="cmd_vel_relay",
        arguments=["/cmd_vel", "/diff_cont/cmd_vel_unstamped"],
        output='screen'
    )

    robot_localization_node = Node(
        package='robot_localization',
        executable='ekf_node',
        name='ekf_node',
        output='screen',
        parameters=[ekf_file, {'use_sim_time': LaunchConfiguration('use_sim_time')}]
    )

    ld = LaunchDescription()

    # Declare args
    ld.add_action(DeclareLaunchArgument(
        name='use_sim_time', default_value='True', description='Use simulation (Gazebo) time'))
    ld.add_action(DeclareLaunchArgument(
        name='model', default_value=default_model_path, description='Absolute path to robot model file'))

    # Add nodes (ros2_control_node before spawners)
    ld.add_action(robot_state_publisher_node)
    ld.add_action(joint_state_publisher_node)
    ld.add_action(ros2_control_node)
    ld.add_action(spawn_joint_state_broadcaster)
    ld.add_action(spawn_diff_cont)
    ld.add_action(cmd_vel_relay)
    ld.add_action(robot_localization_node)

    return ld
