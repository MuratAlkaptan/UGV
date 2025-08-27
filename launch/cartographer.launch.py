from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    return LaunchDescription([
        # Cartographer node
        Node(
            package='cartographer_ros',
            executable='cartographer_node',
            name='cartographer_node',
            output='screen',
            arguments=[
                '-configuration_directory', '~/sam/colcon_ws/src/sam_bot_description/config',
                '-configuration_basename', 'rovalp.lua',
            ],
            remappings=[
                ('/scan', '/scan'),
            ],
        ),

        # Occupancy grid node (publishes /map)
        Node(
            package='cartographer_ros',
            executable='occupancy_grid_node',
            name='occupancy_grid_node',
            output='screen',
            arguments=['-resolution', '0.05', '-publish_period_sec', '1.0'],
        ),
    ])

