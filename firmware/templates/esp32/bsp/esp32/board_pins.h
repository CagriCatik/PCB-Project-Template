#pragma once
// Set only after reviewing carrier-pins.csv and the actual schematic.
// Do not use LED_BUILTIN blindly: the DevKit may have an addressable RGB LED.
#define BSP_STATUS_GPIO (-1)
#define BSP_STATUS_ACTIVE_LOW 0
