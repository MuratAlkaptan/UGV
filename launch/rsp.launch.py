from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, Command
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('rovalp')
    default_model_path = os.path.join(pkg_share, 'src', 'description', 'robot.urdf.xacro')

    # Robot State Publisher node
    robot_state_publisher_node = Node(
        package='robot_state_publisher',
        executable='robot_state_publisher',
        parameters=[{'robot_description': Command(['xacro ', LaunchConfiguration('model')])}],
        output='screen'
    )

    ld = LaunchDescription()

    # Arguments
    ld.add_action(DeclareLaunchArgument(
        name='model',
        default_value=default_model_path,
        description='Absolute path to robot model file'
    ))

    ld.add_action(robot_state_publisher_node)

    return ld
