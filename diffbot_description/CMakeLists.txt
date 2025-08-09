cmake_minimum_required(VERSION 3.8)
project(diffbot_description)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
find_package(xacro REQUIRED)
find_package(robot_state_publisher REQUIRED)

install(DIRECTORY urdf
  DESTINATION share/${PROJECT_NAME}
)

add_custom_target(
  generate_urdf ALL
  COMMAND env XACRO_PATH=${CMAKE_CURRENT_SOURCE_DIR}/urdf xacro
    ${CMAKE_CURRENT_SOURCE_DIR}/urdf/robot.urdf.xacro
    -o ${CMAKE_CURRENT_BINARY_DIR}/robot.urdf
  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/urdf/robot.urdf.xacro
)


install(FILES
  ${CMAKE_CURRENT_BINARY_DIR}/robot.urdf
  DESTINATION share/${PROJECT_NAME}
)
install(
  DIRECTORY launch
  DESTINATION share/${PROJECT_NAME}
  FILES_MATCHING PATTERN "*.launch.py"
)
install(
  DIRECTORY config
  DESTINATION share/${PROJECT_NAME}
  FILES_MATCHING PATTERN "*.yaml"
)
if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()
ament_package()
