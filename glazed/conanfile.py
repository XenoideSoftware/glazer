import os
import shutil

import jinja2
from conan import ConanFile
from conan.tools.files import copy


class GlazedConan(ConanFile):
    name = "glazed"
    version = "0.1.0"  # lockstep with glazer; version file (source of truth)
    description = "Generated OpenGL/ES bindings produced by the Glaze generator"
    license = "MIT"
    python_requires = "xenoide-base/0.1.1"
    python_requires_extend = "xenoide-base.XenoideCMake"
    package_type = "library"
    capture_commit = True

    options = {
        "apis": ["ANY"],
        "language": ["c", "cpp", "both"],
        "extension_vendors": ["ANY"],
        "extensions": ["ANY"],
        "shared": [True, False],
        "fPIC": [True, False],
        "with_docs": [True, False],
    }

    default_options = {
        "apis": "gl:3.3,gl_compat:4.6,gles1:1.0,gles2:3.2",
        "language": "cpp",
        "extension_vendors": "",
        "extensions": "",
        "shared": False,
        "fPIC": True,
        "with_docs": True,
    }

    def init(self):
        super().init()
        self.options.with_tests = False

    exports_sources = ("templates/*",)
    exports = "conandata.yml"

    def config_options(self):
        if self.settings.os == "Windows":
            del self.options.fPIC

    def configure(self):
        if self.options.shared:
            self.options.rm_safe("fPIC")

    def build_requirements(self):
        self.tool_requires("glazer/0.1.0")

    def source(self):
        # Every registry is pinned to an immutable commit in conandata.yml.
        for name, entry in self.conan_data["sources"].items():
            dest = os.path.join(self.source_folder, name)
            if os.path.isdir(os.path.join(dest, ".git")):
                continue
            os.makedirs(dest, exist_ok=True)
            self.run(f'git init "{dest}"')
            self.run(f'git -C "{dest}" remote add origin {entry["url"]}')
            sparse = entry.get("sparse") or []
            if sparse:
                self.run(f'git -C "{dest}" sparse-checkout init --cone')
                self.run(f'git -C "{dest}" sparse-checkout set ' + " ".join(sparse))
            self.run(f'git -C "{dest}" fetch --depth 1 origin {entry["commit"]}')
            self.run(f'git -C "{dest}" checkout --force FETCH_HEAD')

    # ------------------------------------------------------------------ build

    def build(self):
        # -------------------- Phase B: run the glaze generator --------------------
        api_list = [a.strip() for a in str(self.options.apis).split(",") if a.strip()]

        langs_args = []
        if self.options.language in ("c", "cpp", "both"):
            langs_args.extend(["--lang", "c"])
        if self.options.language in ("cpp", "both"):
            langs_args.extend(["--lang", "cpp"])

        out_dir = os.path.join(self.build_folder, "generated")
        os.makedirs(out_dir, exist_ok=True)

        refpages_dir = os.path.join(self.source_folder, "OpenGL-Refpages")
        refpages_args = []
        if self.options.with_docs and os.path.isdir(refpages_dir):
            refpages_args = ["--refpages-dir", refpages_dir]

        ext_vendor_args = []
        if str(self.options.extension_vendors).strip():
            ext_vendor_args = ["--extension-vendors",
                               str(self.options.extension_vendors)]
        ext_name_args = []
        if str(self.options.extensions).strip():
            ext_name_args = ["--extensions", str(self.options.extensions)]

        registry_path = os.path.join(
            self.source_folder, "OpenGL-Registry", "xml", "gl.xml")

        # The glaze binary is on PATH thanks to glazer's buildenv_info.
        cmd = [
            "glaze",
            "generate",
            "--registry", registry_path,
            "--output-dir", out_dir,
        ] + langs_args + refpages_args + ext_vendor_args + ext_name_args

        for api_item in api_list:
            cmd.extend(["--api", api_item])

        self.output.info(f"Running generator: {' '.join(cmd)}")
        self.run(" ".join(f'"{c}"' if " " in c else c for c in cmd))

        # Vendor khrplatform.h alongside the generated headers so the C
        # loader compiles without any external KHR include path.
        khr_src = os.path.join(
            self.source_folder, "EGL-Registry", "api", "KHR", "khrplatform.h")
        khr_dst_dir = os.path.join(out_dir, "include", "KHR")
        os.makedirs(khr_dst_dir, exist_ok=True)
        shutil.copy2(khr_src, khr_dst_dir)

        # -------------------- Phase C: build the generated C loader ---------------
        if self.options.language in ("c", "cpp", "both"):
            templates_dir = os.path.join(self.source_folder, "templates")
            env = jinja2.Environment(
                loader=jinja2.FileSystemLoader(templates_dir),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
            )
            template = env.get_template("cmake/CMakeLists.txt.j2")
            api_names = [a.split(":")[0] for a in api_list]
            cmake_content = template.render(
                apis=api_names,
                lib_type="SHARED" if self.options.shared else "STATIC",
                shared=bool(self.options.shared),
                out_dir=out_dir.replace("\\", "/"),
            )

            c_src_dir = os.path.join(self.build_folder, "c-loader-src")
            c_build_dir = os.path.join(self.build_folder, "c-loader-build")
            os.makedirs(c_src_dir, exist_ok=True)
            os.makedirs(c_build_dir, exist_ok=True)
            with open(os.path.join(c_src_dir, "CMakeLists.txt"), "w") as f:
                f.write(cmake_content)

            toolchain = os.path.join(self.generators_folder, "conan_toolchain.cmake")
            configure_cmd = [
                "cmake",
                "-S", c_src_dir,
                "-B", c_build_dir,
                f"-DCMAKE_TOOLCHAIN_FILE={toolchain}",
                "-DCMAKE_POLICY_DEFAULT_CMP0091=NEW",
                f"-DCMAKE_BUILD_TYPE={self.settings.build_type}",
            ]
            if self.settings.build_type == "Debug":
                configure_cmd.append("-DGLAZE_DEBUG=ON")
            self.run(" ".join(f'"{c}"' for c in configure_cmd))

            build_cmd = [
                "cmake",
                "--build", c_build_dir,
                "--config", str(self.settings.build_type),
            ]
            self.run(" ".join(f'"{c}"' for c in build_cmd))

    def package(self):
        out_dir = os.path.join(self.build_folder, "generated")
        copy(self, "*.h",
             src=os.path.join(out_dir, "include"),
             dst=os.path.join(self.package_folder, "include"))
        copy(self, "*.hpp",
             src=os.path.join(out_dir, "include"),
             dst=os.path.join(self.package_folder, "include"))

        if self.options.language in ("c", "cpp", "both"):
            copy(self, "*.a",
                 src=self.build_folder,
                 dst=os.path.join(self.package_folder, "lib"),
                 keep_path=False)
            copy(self, "*.lib",
                 src=self.build_folder,
                 dst=os.path.join(self.package_folder, "lib"),
                 keep_path=False)
            copy(self, "*.so*",
                 src=self.build_folder,
                 dst=os.path.join(self.package_folder, "lib"),
                 keep_path=False)
            copy(self, "*.dylib",
                 src=self.build_folder,
                 dst=os.path.join(self.package_folder, "lib"),
                 keep_path=False)
            copy(self, "*.dll",
                 src=self.build_folder,
                 dst=os.path.join(self.package_folder, "bin"),
                 keep_path=False)

    def package_info(self):
        self.cpp_info.set_property("cmake_file_name", "glaze")
        self.cpp_info.set_property("cmake_target_name", "glaze::glaze")

        api_list = [a.strip() for a in str(self.options.apis).split(",") if a.strip()]
        debug_build = self.settings.build_type == "Debug"

        if self.options.language in ("cpp", "both"):
            raii = self.cpp_info.components["raii"]
            raii.set_property("cmake_target_name", "glaze::raii")
            raii.includedirs = ["include"]
            raii.bindirs = []
            raii.libdirs = []
            if debug_build:
                raii.defines = ["GLAZE_DEBUG"]

        for api_item in api_list:
            api_name = api_item.split(":")[0]
            comp = self.cpp_info.components[api_name]
            comp.set_property("cmake_target_name", f"glaze::{api_name}")
            comp.includedirs = ["include"]

            if self.options.language in ("c", "cpp", "both"):
                comp.libs = [f"glaze_{api_name}"]
                if self.options.shared:
                    comp.defines = ["GLAZE_DLL"]
            else:
                comp.bindirs = []
                comp.libdirs = []

            if debug_build:
                comp.defines.append("GLAZE_DEBUG")

            if self.options.language in ("cpp", "both"):
                hwrap = self.cpp_info.components[f"{api_name}_handle"]
                hwrap.set_property("cmake_target_name",
                                   f"glaze::{api_name}_handle")
                hwrap.includedirs = ["include"]
                hwrap.bindirs = []
                hwrap.libdirs = []
                hwrap.requires = [api_name]
                if debug_build:
                    hwrap.defines = ["GLAZE_DEBUG"]
