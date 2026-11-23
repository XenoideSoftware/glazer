import os

from conan import ConanFile
from conan.tools.files import copy


class GlazerConan(ConanFile):
    name = "glazer"
    version = "0.1.0"  # lockstep with glazed; version file (source of truth)
    description = "Glaze OpenGL binding generator CLI tool"
    license = "MIT"
    python_requires = "xenoide-base/0.1.1"
    python_requires_extend = "xenoide-base.XenoideCMake"
    package_type = "application"
    build_info_prefix = "GLAZE"
    capture_commit = True

    options = {}

    def init(self):
        super().init()
        # The unit suite is the product's safety net; a default build must
        # exercise it (a task that "passes" with 0 tests hides regressions).
        self.options.with_tests = True

    exports_sources = (
        "CMakeLists.txt",
        "cmake/*",
        "src/*",
    )

    def requirements(self):
        self.requires("pugixml/1.15")
        self.requires("inja/3.4.0")
        self.requires("nlohmann_json/3.12.0")
        self.requires("cxxopts/3.3.1")

    def xenoide_toolchain(self, tc):
        tc.variables["GLAZE_CPP_WITH_TESTS"] = bool(self.options.with_tests)

    def build(self):
        super().build()
        if self.options.with_tests:
            from conan.tools.cmake import CMake
            CMake(self).test()

    def package(self):
        # Package only the glaze CLI binary. Patterns are wildcarded so they
        # match through the per-config subdir (Debug/Release) that some
        # generators insert between bin/ and the executable.
        copy(self, "*glaze",
             src=os.path.join(self.build_folder, "bin"),
             dst=os.path.join(self.package_folder, "bin"),
             keep_path=False)
        copy(self, "*glaze.exe",
             src=os.path.join(self.build_folder, "bin"),
             dst=os.path.join(self.package_folder, "bin"),
             keep_path=False)

    def package_info(self):
        self.cpp_info.frameworkdirs = []
        self.cpp_info.libdirs = []
        self.cpp_info.resdirs = []
        self.cpp_info.includedirs = []

        bindir = os.path.join(self.package_folder, "bin")
        self.buildenv_info.prepend_path("PATH", bindir)
