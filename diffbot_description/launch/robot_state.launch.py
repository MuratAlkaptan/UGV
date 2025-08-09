
from launch import LaunchDescription
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory
import os

def generate_launch_description():
    pkg_share = get_package_share_directory('diffbot_description')
    urdf = os.path.join(pkg_share, 'robot.urdf')
    return LaunchDescription([
        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': open(urdf).read()}]
        ),
        # optional: rviz to visualize
        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', os.path.join(pkg_share, 'rviz', 'diffbot.rviz')]
        ),
    
        # you can also spin up joint_state_publisher_gui here if needed:
        # Node(package='joint_state_publisher_gui', 				    executable='joint_state_publisher_gui')
 
    ])

