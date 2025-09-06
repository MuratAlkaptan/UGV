from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('rovalp')
    default_model_path = os.path.join(pkg_share, 'src', 'description', 'robot.urdf.xacro')
    controllers_file = os.path.join(pkg_share, 'config', 'controllers.yaml')
    ekf_file = os.path.join(pkg_share, 'config', 'ekf.yaml')
    robot_description = Command([
        'xacro ', '/home/murat/rovalp_ws/src/rovalp/src/description/robot.urdf.xacro'
    ])
    # Include robot_state_publisher launch file
    rsp_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(pkg_share, 'launch', 'rsp.launch.py')
        ),
        launch_arguments={'model': LaunchConfiguration('model')}.items()
    )

    # Node: joint_state_publisher
    joint_state_publisher_node = Node(
        package='joint_state_publisher',
        executable='joint_state_publisher',
        name='joint_state_publisher',
        arguments=[default_model_path],
        output='screen'
    )

    # ros2_control (controller_manager)
    ros2_control_node = Node(
        package="controller_manager",
        executable="ros2_control_node",
        parameters=[controllers_file,
                    {'robot_description': robot_description}],
        output="screen"
    )

    # Spawners with delays
    spawn_joint_state_broadcaster = TimerAction(
        period=3.0,
        actions=[Node(
            package="controller_manager",
            executable="spawner",
            arguments=["joint_state_broadcaster", "-c", "/controller_manager"],
            output="screen"
        )]
    )

    spawn_diff_cont = TimerAction(
        period=4.0,
        actions=[Node(
            package="controller_manager",
            executable="spawner",
            arguments=["diff_cont", "-c", "/controller_manager"],
            output="screen"
        )]
    )

    # Relay
    cmd_vel_relay = Node(
        package="topic_tools",
        executable="relay",
        name="cmd_vel_relay",
        arguments=["/cmd_vel", "/diff_cont/cmd_vel_unstamped"],
        output='screen'
    )

    # Localization
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
        name='use_sim_time', default_value='False', description='Use simulation (Gazebo) time'))
    ld.add_action(DeclareLaunchArgument(
        name='model', default_value=default_model_path, description='Absolute path to robot model file'))

    # Add nodes
    ld.add_action(rsp_launch)
    ld.add_action(joint_state_publisher_node)
    ld.add_action(ros2_control_node)
    ld.add_action(spawn_joint_state_broadcaster)
    ld.add_action(spawn_diff_cont)
    ld.add_action(cmd_vel_relay)
    ld.add_action(robot_localization_node)

    return ld
