# Firmware build: host unit tests by default; a target is selected with FW_TARGET.
cmake_minimum_required(VERSION 3.20)
project(firmware C)

set(CMAKE_C_STANDARD 11)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(FW_TARGET "host" CACHE STRING "Firmware target: host | stm32")
option(FW_BUILD_TESTS "Build host unit tests" OFF)

# Platform-independent application logic; sees only the BSP interface header.
add_library(app STATIC app/src/heartbeat.c)
target_include_directories(app PUBLIC app/include bsp/include)
if(CMAKE_C_COMPILER_ID MATCHES "GNU|Clang")
  target_compile_options(app PRIVATE -Wall -Wextra -Wconversion -Werror)
endif()

if(FW_BUILD_TESTS)
  if(NOT FW_TARGET STREQUAL "host")
    message(FATAL_ERROR "Unit tests run on the host only (FW_TARGET=host).")
  endif()
  enable_testing()
  add_executable(test_heartbeat tests/test_heartbeat.c)
  target_link_libraries(test_heartbeat PRIVATE app)
  add_test(NAME heartbeat COMMAND test_heartbeat)
endif()

if(FW_TARGET STREQUAL "stm32")
  include(cmake/stm32-target.cmake)
endif()
