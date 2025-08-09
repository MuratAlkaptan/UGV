# sim_bringup.launch.py

from launch import LaunchDescription
from launch.substitutions import LaunchConfiguration
from launch.actions import ExecuteProcess, TimerAction, IncludeLaunchDescription
from launch_ros.actions import Node
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.substitutions import FindPackageShare

import os
from ament_index_python.packages import get_package_share_directory
import xacro

robot_description = xacro.process_file(
    "/home/murat/ika_ws/src/diffbot_description/urdf/gz_robot.urdf.xacro"
).toxml()

use_sim_time = True
empty_map = "/home/murat/ika_ws/src/diffbot_description/maps/empty_map.yaml"

# === SLAM Toolbox inline parameters ===
slam_params = {
    'use_sim_time': True,
    'slam_mode': True,
    'map_file_name': "",
    'publish_period_sec': 1.0,
    'resolution': 0.05,
    'scan_topic': '/scan',
    'odom_topic': '/odom',
    'transform_publish_period': 0.1,
    'map_publish_period': 0.5
}

# === Nav2 inline parameters ===
nav2_params = {
    'amcl': {
        'ros__parameters': {
            'use_sim_time': True,
            'odom_frame_id': 'odom',
            'base_frame_id': 'base_link',
            'scan_topic': '/scan',
            'alpha1': 0.2,
            'alpha2': 0.2,
            'alpha3': 0.2,
            'alpha4': 0.2,
            'alpha5': 0.2,
            'kld_err': 0.05,
            'kld_z': 0.99,
            'max_particles': 200,
            'min_particles': 50
        }
    },
    'planner_server': {
        'ros__parameters': {
            'use_sim_time': True,
            'expected_planner_frequency': 20.0,
            'planner_plugin_ids': ["GridBased"],
            'GridBased': {
                'plugin': "nav2_navfn_planner/NavfnPlanner"
            }
        }
    },
    'controller_server': {
        'ros__parameters': {
            'use_sim_time': True,
            'expected_controller_frequency': 20.0,
            'controller_plugin_ids': ["FollowPath"],
            'FollowPath': {
                'plugin': "nav2_regulated_pure_pursuit_controller/RegulatedPurePursuitController",
                'lookahead_distance': 0.5
            }
        }
    },
    'bt_navigator': {
        'ros__parameters': {
            'use_sim_time': True,
            'default_bt_xml_filename': "behavior_trees/navigate_w_replanning_and_recovery.xml",
            'plugin_lib_names': []
        }
    },
    'recoveries_server': {
        'ros__parameters': {
            'use_sim_time': True
        }
    }
}


def generate_launch_description():
    pkg_share = get_package_share_directory('diffbot_description')

    return LaunchDescription([
        ExecuteProcess(
            cmd=['gazebo', '--verbose', '-s', 'libgazebo_ros_init.so', '-s', 'libgazebo_ros_factory.so'],
            output='screen'
        ),

        ExecuteProcess(
            cmd=['MicroXRCEAgent', 'udp4', '-p', '8888'],
            output='screen'
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            output='screen',
            parameters=[{'robot_description': robot_description, 'use_sim_time': use_sim_time}]
        ),

        TimerAction(
            period=5.0,
            actions=[
                Node(
                    package='gazebo_ros',
                    executable='spawn_entity.py',
                    arguments=['-entity', 'diffbot', '-topic', 'robot_description', '-x', '0', '-y', '0', '-z', '0.1'],
                    output='screen'
                )
            ]
        ),

        Node(
            package='slam_toolbox',
            executable='async_slam_toolbox_node',
            name='slam_toolbox',
            output='screen',
            parameters=[slam_params]
        ),

        # Nav2 Bringup (all nodes must get their own params!)
        Node(
            package='nav2_amcl',
            executable='amcl',
            name='amcl',
            output='screen',
            parameters=[nav2_params['amcl']]
        ),
        Node(
            package='nav2_planner',
            executable='planner_server',
            name='planner_server',
            output='screen',
            parameters=[nav2_params['planner_server']]
        ),
        Node(
            package='nav2_controller',
            executable='controller_server',
            name='controller_server',
            output='screen',
            parameters=[nav2_params['controller_server']]
        ),
        Node(
            package='nav2_bt_navigator',
            executable='bt_navigator',
            name='bt_navigator',
            output='screen',
            parameters=[nav2_params['bt_navigator']]
        ),
        Node(
            package='nav2_recoveries',
            executable='recoveries_server',
            name='recoveries_server',
            output='screen',
            parameters=[nav2_params['recoveries_server']]
        ),

        Node(
            package='rviz2',
            executable='rviz2',
            name='rviz2',
            output='screen',
            arguments=['-d', os.path.join(pkg_share, 'config', 'diffbot.rviz')],
            parameters=[{'use_sim_time': use_sim_time}]
        ),
    ])

