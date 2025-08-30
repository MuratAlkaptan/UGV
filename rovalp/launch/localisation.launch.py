from launch import LaunchDescription
from launch_ros.actions import Node
from launch.actions import TimerAction

def generate_launch_description():

    # AMCL node
    amcl_node = Node(
        package='nav2_amcl',
        executable='amcl',
        name='amcl',
        output='screen',
        parameters=[{'use_sim_time': True}]
    )

    # Publisher for initial pose (delayed so AMCL is ready)
    initial_pose_pub = TimerAction(
        period=3.0,  # wait 3s before publishing
        actions=[
            Node(
                package='ros2_topic',
                executable='ros2_topic',
                name='initial_pose_pub',
                arguments=[
                    'pub', '--once', '/initialpose',
                    'geometry_msgs/PoseWithCovarianceStamped',
                    "{header: {frame_id: 'map'}, pose: {pose: {position: {x: 0.0, y: 0.0, z: 0.0}, orientation: {z: 0.0, w: 1.0}}}}"
                ]
            )
        ]
    )

    return LaunchDescription([
        amcl_node,
        initial_pose_pub
    ])

