#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan

class LaserRecorder(Node):
    def __init__(self):
        super().__init__('laser_recorder')
        self.subscription = self.create_subscription(
            LaserScan,
            '/scan',
            self.scan_callback,
            10
        )
        self.file = open('laserscan.txt', 'w')
        self.get_logger().info("Recording LaserScan data to laserscan.txt")

    def scan_callback(self, msg):
        # Save ranges as comma-separated string
        ranges_str = ','.join([str(r) for r in msg.ranges])
        self.file.write(ranges_str + '\n')
        self.get_logger().info("Saved one scan frame")

def main(args=None):
    rclpy.init(args=args)
    node = LaserRecorder()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.file.close()
        node.destroy_node()
        rclpy.shutdown()

if __name__ == "__main__":
    main()

