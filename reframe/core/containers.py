# Copyright 2016-2021 Swiss National Supercomputing Centre (CSCS/ETH Zurich)
# ReFrame Project Developers. See the top-level LICENSE file for details.
#
# SPDX-License-Identifier: BSD-3-Clause

import abc
import warnings

import reframe.core.fields as fields
import reframe.utility.typecheck as typ
from reframe.core.exceptions import ContainerError


class ContainerPlatform(abc.ABC):
    '''The abstract base class of any container platform.'''

    #: The default mount location of the test case stage directory inside the
    #: container
    RFM_STAGEDIR = '/rfm_workdir'

    #: The container image to be used for running the test.
    #:
    #: :type: :class:`str` or :class:`None`
    #: :default: :class:`None`
    image = fields.TypedField(str, type(None))

    #: The command to be executed within the container.
    #:
    #: If no command is given, then the default command of the corresponding
    #: container image is going to be executed.
    #:
    #: ..versionchanged:: 3.5
    #:   Changed the attribute name from `commands` to `command` and its type
    #:   to a string.
    #:
    #: :type: :class:`str` or :class:`None`
    #: :default: :class:`None`
    command = fields.TypedField(str, type(None))

    #: The commands to be executed within the container.
    #:
    #: ..versionchanged:: 3.5
    #:   The `commands` field is now deprecated.
    #:
    #: :type: :class:`list[str]`
    #: :default: ``[]``
    commands = fields.DeprecatedField(
        fields.TypedField(typ.List[str]),
        'The `commands` field is deprecated, please use the `command` field '
        'to set the command to be executed by the container.', 1
    )

    #: Pull the container image before running.
    #:
    #: This does not have any effect for the `Singularity` container platform.
    #:
    #: ..versionadded:: 3.5
    #:
    #: :type: :class:`bool`
    #: :default: ``True``
    pull_image = fields.TypedField(bool)

    #: List of mount point pairs for directories to mount inside the container.
    #:
    #: Each mount point is specified as a tuple of
    #: ``(/path/in/host, /path/in/container)``. The stage directory of the
    #: ReFrame test is always mounted under ``/rfm_workdir`` inside the
    #: container, independelty of this field.
    #:
    #: :type: :class:`list[tuple[str, str]]`
    #: :default: ``[]``
    mount_points = fields.TypedField(typ.List[typ.Tuple[str, str]])

    #: Additional options to be passed to the container runtime when executed.
    #:
    #: :type: :class:`list[str]`
    #: :default: ``[]``
    options = fields.TypedField(typ.List[str])

    #: The working directory of ReFrame inside the container.
    #:
    #: This is the directory where the test's stage directory is mounted inside
    #: the container. This directory is always mounted regardless if
    #: :attr:`mount_points` is set or not.
    #:
    #: ..versionchanged:: 3.5
    #:   The `commands` field is now deprecated.
    #:
    #: :type: :class:`str`
    #: :default: ``/rfm_workdir``
    workdir = fields.DeprecatedField(
        fields.TypedField(str, type(None)),
        'The `workdir` field is deprecated, please use the `options` field to '
        'set the container working directory', 1
    )

    def __init__(self):
        self.image = None
        self.command = None
        with warnings.catch_warnings(record=True):
            self.commands = []
            self.workdir = self.RFM_STAGEDIR

        self.mount_points  = []
        self.options = []
        self.pull_image = True

    @abc.abstractmethod
    def emit_prepare_commands(self):
        '''Returns commands for preparing this container for running.

        Such a command could be for pulling the container image from a
        repository.

        .. note:

            This method is relevant only to developers of new container
            platform backends.

        :meta private:
        '''

    @abc.abstractmethod
    def launch_command(self):
        '''Returns the command for running :attr:`commands` with this container
        platform.

        .. note:
            This method is relevant only to developers of new container
            platforms.

        :meta private:
        '''

    def validate(self):
        if self.image is None:
            raise ContainerError('no image specified')

    def __str__(self):
        return type(self).__name__

    def __rfm_json_encode__(self):
        return str(self)


class Docker(ContainerPlatform):
    '''Container platform backend for running containers with `Docker
    <https://www.docker.com/>`__.'''

    def emit_prepare_commands(self):
        return [f'docker pull {self.image}'] if self.pull_image else []

    def launch_command(self):
        super().launch_command()
        run_opts = [f'-v "{mp[0]}":"{mp[1]}"' for mp in self.mount_points]
        run_opts += self.options

        run_cmd = 'docker run --rm %s %s bash -c ' % (' '.join(run_opts),
                                                      self.image)

        if self.command:
            return (f'docker run --rm {" ".join(run_opts)} '
                    f'{self.image} {self.command}')

        if self.commands:
            return (f"docker run --rm {' '.join(run_opts)} {self.image} "
                    f"bash -c 'cd {self.workdir}; {'; '.join(self.commands)}'")

        return (f'docker run --rm {" ".join(run_opts)} {self.image}')


class Sarus(ContainerPlatform):
    '''Container platform backend for running containers with `Sarus
    <https://sarus.readthedocs.io>`__.'''

    #: Enable MPI support when launching the container.
    #:
    #: :type: boolean
    #: :default: :class:`False`
    with_mpi = fields.TypedField(bool)

    def __init__(self):
        super().__init__()
        self.with_mpi = False

    def emit_prepare_commands(self):
        # The format that Sarus uses to call the images is
        # <reposerver>/<user>/<image>:<tag>. If an image was loaded
        # locally from a tar file, the <reposerver> is 'load'.
        if not self.pull_image or self.image.startswith('load/'):
            return []
        else:
            return [f'sarus pull {self.image}']

    def launch_command(self):
        super().launch_command()
        run_opts = [f'--mount=type=bind,source="{mp[0]}",destination="{mp[1]}"'
                    for mp in self.mount_points]
        if self.with_mpi:
            run_opts.append('--mpi')

        run_opts += self.options

        if self.command:
            return (f'sarus run {" ".join(run_opts)} {self.image} '
                    f'{self.command}')

        if self.commands:
            return (f"sarus run {' '.join(run_opts)} {self.image} "
                    f"bash -c 'cd {self.workdir}; {'; '.join(self.commands)}'")

        return f'sarus run {" ".join(run_opts)} {self.image}'


class Shifter(ContainerPlatform):
    '''Container platform backend for running containers with `Shifter
    <https://www.nersc.gov/research-and-development/user-defined-images/>`__.
    '''

    #: Enable MPI support when launching the container.
    #:
    #: :type: boolean
    #: :default: :class:`False`
    with_mpi = fields.TypedField(bool)

    def __init__(self):
        super().__init__()
        self.with_mpi = False

    def emit_prepare_commands(self):
        # The format that Shifter uses to call the images is
        # <reposerver>/<user>/<image>:<tag>. If an image was loaded
        # locally from a tar file, the <reposerver> is 'load'.
        if not self.pull_image or self.image.startswith('load/'):
            return []
        else:
            return [f'shifter pull {self.image}']

    def launch_command(self):
        super().launch_command()
        run_opts = [f'--mount=type=bind,source="{mp[0]}",destination="{mp[1]}"'
                    for mp in self.mount_points]
        if self.with_mpi:
            run_opts.append('--mpi')

        run_opts += self.options

        if self.command:
            return (f'shifter run {" ".join(run_opts)} {self.image} '
                    f'{self.command}')

        if self.commands:
            return (f"shifter run {' '.join(run_opts)} {self.image} "
                    f"bash -c 'cd {self.workdir}; {'; '.join(self.commands)}'")

        return f'shifter run {" ".join(run_opts)} {self.image}'


class Singularity(ContainerPlatform):
    '''Container platform backend for running containers with `Singularity
    <https://sylabs.io/>`__.'''

    #: Enable CUDA support when launching the container.
    #:
    #: :type: boolean
    #: :default: :class:`False`
    with_cuda = fields.TypedField(bool)

    def __init__(self):
        super().__init__()
        self.with_cuda = False

    def emit_prepare_commands(self):
        return []

    def launch_command(self):
        super().launch_command()
        run_opts = [f'-B"{mp[0]}:{mp[1]}"' for mp in self.mount_points]
        if self.with_cuda:
            run_opts.append('--nv')

        run_opts += self.options
        if self.command:
            return (f'singularity exec {" ".join(run_opts)} '
                    f'{self.image} {self.command}')

        if self.commands:
            return (f"singularity exec {' '.join(run_opts)} {self.image} "
                    f"bash -c 'cd {self.workdir}; {'; '.join(self.commands)}'")

        return f'singularity run {" ".join(run_opts)} {self.image}'


class ContainerPlatformField(fields.TypedField):
    def __init__(self, *other_types):
        super().__init__(ContainerPlatform, *other_types)

    def __set__(self, obj, value):
        if isinstance(value, str):
            try:
                value = globals()[value]()
            except KeyError:
                raise ValueError(
                    f'unknown container platform: {value}') from None

        super().__set__(obj, value)
