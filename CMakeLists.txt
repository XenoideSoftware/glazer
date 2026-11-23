cmake_minimum_required (VERSION 3.25)
project (glaze-cpp LANGUAGES CXX)

include(XenoideConfig)

option (GLAZE_CPP_WITH_TESTS "Build the Catch2 unit test suite" OFF)
option (GLAZE_CPP_WARNINGS_AS_ERRORS "Treat warnings as errors" OFF)

# Flatten binary output so the conanfile.py recipe can locate glaze with
# a single well-known path across single- and multi-config generators.
if (NOT CMAKE_RUNTIME_OUTPUT_DIRECTORY)
    set (CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
endif()

# Compatibility shim for the subtree, which links glaze::interface. It is a
# real interface target forwarding to the devkit one (CMake cannot alias an
# alias).
add_library(glaze_interface INTERFACE)
target_link_libraries(glaze_interface INTERFACE xenoide::interface)
add_library(glaze::interface ALIAS glaze_interface)

add_subdirectory (src)
