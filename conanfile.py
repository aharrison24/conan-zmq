#!/usr/bin/env python
# -*- coding: utf-8 -*-

from conans import ConanFile, tools, CMake
import os
import fnmatch


class ZMQConan(ConanFile):
    name = "zmq"
    version = "4.2.2"
    url = "https://github.com/bincrafters/conan-zmq"
    description = "ZeroMQ is a community of projects focused on decentralized messaging and computing"
    license = "LGPL-3.0"
    exports = ["LICENSE.md"]
    settings = "os", "arch", "compiler", "build_type"
    options = {"shared": [True, False], "fPIC": [True, False], "encryption": [None, "libsodium", "tweetnacl"]}
    default_options = "shared=False", "fPIC=True", "encryption=libsodium"
    generators = ['cmake']

    def source(self):
        # see https://github.com/zeromq/libzmq/issues/2597
        extracted_dir = "libzmq-%s" % self.version
        archive_name = "v%s.tar.gz" % self.version
        source_url = "https://github.com/zeromq/libzmq/archive/%s" % archive_name
        tools.get(source_url)
        os.rename(extracted_dir, "sources")

        # Need CMP0042 and CMP0068 to make rpaths work properly.
        tools.replace_in_file(os.path.join('sources', 'CMakeLists.txt'),
                      'cmake_minimum_required (VERSION 2.8.12)',
                      r'''cmake_minimum_required (VERSION 3.10)

# use, i.e. don't skip the full RPATH for the build tree
SET(CMAKE_SKIP_BUILD_RPATH FALSE)

# when building, don't use the install RPATH already
# (but later on when installing)
SET(CMAKE_BUILD_WITH_INSTALL_RPATH FALSE)

SET(CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/lib")

# add the automatically determined parts of the RPATH
# which point to directories outside the build tree to the install RPATH
SET(CMAKE_INSTALL_RPATH_USE_LINK_PATH TRUE)

# the RPATH to be used when installing, but only if it's not a system directory
LIST(FIND CMAKE_PLATFORM_IMPLICIT_LINK_DIRECTORIES "${CMAKE_INSTALL_PREFIX}/lib" isSystemDir)
IF("${isSystemDir}" STREQUAL "-1")
   SET(CMAKE_INSTALL_RPATH "${CMAKE_INSTALL_PREFIX}/lib")
ENDIF()
''')

        # disable precompiled headers
        # fatal error C1083: Cannot open precompiled header file: 'precompiled.pch': Permission denied
        tools.replace_in_file(os.path.join('sources', 'CMakeLists.txt'),
                              "if (MSVC)\n    # default for all sources is to use precompiled header",
                              "if (MSVC_DISABLED)\n    # default for all sources is to use precompiled header")

        # fix PDB location
        tools.replace_in_file(os.path.join('sources', 'CMakeLists.txt'),
                              'install (FILES ${CMAKE_CURRENT_BINARY_DIR}/bin/libzmq',
                              'install (FILES ${CMAKE_BINARY_DIR}/bin/libzmq')

        tools.replace_in_file(os.path.join('sources', 'builds', 'cmake', 'platform.hpp.in'),
                              'HAVE_LIBSODIUM', 'ZMQ_USE_LIBSODIUM')

        tools.replace_in_file(
            "sources/CMakeLists.txt",
            "project (ZeroMQ)",
            """project (ZeroMQ)
include("${CMAKE_BINARY_DIR}/conanbuildinfo.cmake")
set(CMAKE_PREFIX_PATH "${CONAN_CMAKE_MODULE_PATH}")
include(GNUInstallDirs)""",
        )

    def configure(self):
        if self.settings.compiler == 'Visual Studio':
            del self.options.fPIC

    def requirements(self):
        if self.options.encryption == 'libsodium':
            self.requires.add('libsodium/1.0.16@bincrafters/stable')

    def system_requirements(self):
        if self.settings.os == "Linux" and tools.os_info.is_linux:
            if tools.os_info.with_apt:
                arch = ''
                if self.settings.arch == "x86":
                    arch = ':i386'
                elif self.settings.arch == 'x86_64':
                    arch = ':amd64'
                installer = tools.SystemPackageTool()
                installer.install('pkg-config%s' % arch)

    def build_cmake(self):
        cmake = CMake(self)
        if self.settings.compiler != 'Visual Studio':
            cmake.definitions['CMAKE_POSITION_INDEPENDENT_CODE'] = self.options.fPIC
        cmake.definitions['ENABLE_CURVE'] = self.options.encryption is not None
        cmake.definitions['WITH_LIBSODIUM'] = self.options.encryption == "libsodium"
        cmake.definitions['CMAKE_INSTALL_LIBDIR'] = 'lib'
        cmake.configure(source_folder="sources")
        cmake.build()
        cmake.install()

    def build(self):
        if self.settings.compiler == 'Visual Studio':
            with tools.vcvars(self.settings, force=True, filter_known_paths=False):
                self.build_cmake()
        else:
            self.build_cmake()

    def package(self):
        self.copy(pattern="COPYING", src='sources', dst='license')
        if self.options.shared:
            exts = ['*.a']
        else:
            exts = ['*.dll', '*.so*', '*.dylib*']
        for root, _, filenames in os.walk(self.package_folder):
            for ext in exts:
                for filename in fnmatch.filter(filenames, ext):
                    os.unlink(os.path.join(root, filename))

    def package_info(self):
        if self.settings.compiler == 'Visual Studio':
            version = '_'.join(self.version.split('.'))
            if self.settings.build_type == 'Debug':
                runtime = '-gd' if self.options.shared else '-sgd'
            else:
                runtime = '' if self.options.shared else '-s'
            library_name = 'libzmq-mt%s-%s.lib' % (runtime, version)
            self.cpp_info.libs = [library_name, 'ws2_32', 'Iphlpapi']
        else:
            self.cpp_info.libs = ['zmq']
        if self.settings.os == "Linux":
            self.cpp_info.libs.extend(['pthread', 'rt', 'm'])
        if not self.options.shared:
            # zmq has C API, but requires C++ libraries to be lined
            if str(self.settings.compiler) in ['clang', 'gcc', 'apple-clang']:
                if str(self.settings.compiler.libcxx) in ['libstdc++', 'libstdc++11']:
                    self.cpp_info.libs.append('stdc++')
                elif str(self.settings.compiler.libcxx) == 'libc++':
                    self.cpp_info.libs.append('c++')
            self.cpp_info.defines.append('ZMQ_STATIC')
        # contains ZeroMQConfig.cmake
        self.cpp_info.builddirs.append(os.path.join(self.package_folder, 'share', 'cmake', 'ZeroMQ'))
