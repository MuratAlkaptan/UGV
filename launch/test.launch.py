from launch import LaunchDescription
from launch_ros.actions import Node
from launch.substitutions import Command
import os
from ament_index_python.packages import get_package_share_directory

def generate_launch_description():
    controllers_file = os.path.join(get_package_share_directory('rovalp'), 'config', 'controllers.yaml')
    robot_description = Command([
        'xacro ', '/home/murat/rovalp_ws/src/rovalp/src/description/robot.urdf.xacro'
    ])

    return LaunchDescription([
        Node(
            package='controller_manager',
            executable='ros2_control_node',
            parameters=[
                controllers_file,
                {'robot_description': robot_description}]
        )
    ])
