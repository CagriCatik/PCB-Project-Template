# STM32 target integration. The MCU, clock tree, pinout, startup code, linker
# script and compiler flags all come from STM32CubeMX's own CMake output
# (Project Manager > Toolchain/IDE = CMake); this kit never invents them.
# Generated files under bsp/stm32/cubemx are used as-is and never edited here.
set(CUBEMX_DIR "${CMAKE_CURRENT_SOURCE_DIR}/bsp/stm32/cubemx")
if(NOT EXISTS "${CUBEMX_DIR}/cmake/stm32cubemx/CMakeLists.txt")
  message(FATAL_ERROR
    "STM32CubeMX project missing. In STM32CubeMX select your MCU, choose Project Manager > "
    "Toolchain/IDE = CMake and generate into firmware/bsp/stm32/cubemx. "
    "See firmware/bsp/stm32/README.md.")
endif()
set(FW_STATUS_LED "STATUS_LED" CACHE STRING
    "CubeMX user label of the status output GPIO (defines <label>_Pin and <label>_GPIO_Port)")
enable_language(ASM)

# CubeMX's toolchain file passes "-T ${CMAKE_SOURCE_DIR}/<linker script>" because it
# assumes the CubeMX project is the CMake root; here it lives in bsp/stm32/cubemx.
string(REPLACE "${CMAKE_SOURCE_DIR}/" "${CUBEMX_DIR}/" CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS}")

# The generated stm32cubemx package adds its sources to the target named
# ${CMAKE_PROJECT_NAME}, so that executable must exist before add_subdirectory().
add_executable(${CMAKE_PROJECT_NAME} bsp/stm32/bsp_stm32.c)
set_target_properties(${CMAKE_PROJECT_NAME} PROPERTIES SUFFIX ".elf")
add_subdirectory("${CUBEMX_DIR}/cmake/stm32cubemx" stm32cubemx)
target_link_libraries(${CMAKE_PROJECT_NAME} stm32cubemx app)
target_compile_definitions(${CMAKE_PROJECT_NAME} PRIVATE BSP_STATUS_LED=${FW_STATUS_LED})
