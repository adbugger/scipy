from __future__ import division, print_function, absolute_import

import numpy as np
import scipy.linalg
from re import compile as recompile  # compile itself is a builtin function


class Rotation(object):
    """Rotation in 3 dimensions.

    This class will include initializers from different representations,
    converters and some useful algorithms such as quaternion slerp and
    rotation estimation.

    For initializing Rotations usage of `from_...` methods such as
    `from_quaternion` is recommended instead of using `__init__`.

    Methods
    -------
    from_quaternion
    as_quaternion
    from_dcm
    as_dcm
    from_rotvec
    as_rotvec
    """
    def __init__(self, quat, normalized=False):
        self._single = False
        # Try to convert to numpy array
        quat = np.asarray(quat, dtype=float)

        if quat.ndim not in [1, 2] or quat.shape[-1] != 4:
            raise ValueError("Expected `quat` to have shape (4,) or (N x 4), "
                             "got {}.".format(quat.shape))

        # If a single quaternion is given, convert it to a 2D 1 x 4 matrix but
        # set self._single to True so that we can return appropriate objects
        # in the `to_...` methods
        if quat.shape == (4,):
            quat = quat[None, :]
            self._single = True

        if normalized:
            self._quat = quat
        else:
            self._quat = quat.copy()
            # L2 norm of each row
            norms = scipy.linalg.norm(quat, axis=1)

            # Raise ValueError for zero (eps?) norm quaternions
            zero_norms = norms == 0
            if zero_norms.any():
                raise ValueError("Found zero norm quaternions in `quat`.")

            # Normalize each quaternion, ensuring norm is broadcasted along
            # each column.
            self._quat[~zero_norms] /= norms[~zero_norms][:, None]

    @classmethod
    def from_quaternion(cls, quat, normalized=False):
        """Initialize Rotation from quaternions.

        This classmethod returns a `Rotation` object from the input quaternions
        If `normalized` is `True`, then the quaternions are assumed to have
        unit norm, else the quaternions are normalized before the object is
        created.

        Parameters
        ----------
        quat : array_like, shape (N, 4) or (4,)
            Each row is a (possibly non-unit norm) quaternion in scalar-last
            (x, y, z, w) format.
        normalized : boolean, optional
            If this flag is `True`, then it is assumed that the input
            quaternions all have unit norm and are not normalized again.
            Default is False.
        """

        return cls(quat, normalized)

    def as_quaternion(self):
        """Return the quaternion representation of the Rotation.

        This function returns a numpy array of shape (4,) or (N x 4) depending
        on the input that was used to initialize the object.
        """
        if self._single:
            return self._quat[0]
        else:
            return self._quat

    def as_dcm(self):
        """Return the direction cosine matrix representation of the Rotation.

        This function returns a numpy.ndarray of shape (3, 3) or (N, 3, 3)
        depending on the input that was used to initialize the object.
        """

        x = self._quat[:, 0]
        y = self._quat[:, 1]
        z = self._quat[:, 2]
        w = self._quat[:, 3]

        x2 = x * x
        y2 = y * y
        z2 = z * z
        w2 = w * w

        xy = x * y
        zw = z * w
        xz = x * z
        yw = y * w
        yz = y * z
        xw = x * w

        num_rotations = self._quat.shape[0]
        dcm = np.empty((num_rotations, 3, 3))

        dcm[:, 0, 0] = x2 - y2 - z2 + w2
        dcm[:, 1, 0] = 2 * (xy + zw)
        dcm[:, 2, 0] = 2 * (xz - yw)

        dcm[:, 0, 1] = 2 * (xy - zw)
        dcm[:, 1, 1] = - x2 + y2 - z2 + w2
        dcm[:, 2, 1] = 2 * (yz + xw)

        dcm[:, 0, 2] = 2 * (xz + yw)
        dcm[:, 1, 2] = 2 * (yz - xw)
        dcm[:, 2, 2] = - x2 - y2 + z2 + w2

        if self._single:
            return dcm[0]
        else:
            return dcm

    @classmethod
    def from_dcm(cls, dcm):
        """Initialize rotation from direction cosine matrix.

        This classmethod return a `Rotation` object from the input direction
        cosine matrices. If the input matrix is not orthogonal, this method
        creates an approximation using the algorithm described in [1]_.

        Parameters
        ----------
        dcm : array_like, shape (N, 3, 3) or (3, 3)
            A single matrix or a stack of matrices, where `dcm[i]` is the i-th
            matrix.

        References
        ----------
        .. [1] F. Landis Markley, `Unit Quaternion from Rotation Matrix
               <https://arc.aiaa.org/doi/abs/10.2514/1.31730>`_
        """
        is_single = False
        dcm = np.asarray(dcm, dtype=float)

        if dcm.ndim not in [2, 3] or (dcm.shape[-2], dcm.shape[-1]) != (3, 3):
            raise ValueError("Expected `dcm` to have shape (3, 3) or "
                             "(N, 3, 3), got {}".format(dcm.shape))

        # If a single dcm is given, convert it to 3D 1 x 3 x 3 matrix but set
        # self._single to True so that we can return appropriate objects in
        # the `to_...` methods
        if dcm.shape == (3, 3):
            dcm = dcm.reshape((1, 3, 3))
            is_single = True

        num_rotations = dcm.shape[0]

        decision_matrix = np.empty((num_rotations, 4))
        decision_matrix[:, :3] = dcm.diagonal(axis1=1, axis2=2)
        decision_matrix[:, -1] = decision_matrix[:, :3].sum(axis=1)
        choices = decision_matrix.argmax(axis=1)

        quat = np.empty((num_rotations, 4))

        ind = np.nonzero(choices != 3)[0]
        i = choices[ind]
        j = (i + 1) % 3
        k = (j + 1) % 3

        quat[ind, i] = 1 - decision_matrix[ind, -1] + 2 * dcm[ind, i, i]
        quat[ind, j] = dcm[ind, j, i] + dcm[ind, i, j]
        quat[ind, k] = dcm[ind, k, i] + dcm[ind, i, k]
        quat[ind, 3] = dcm[ind, k, j] - dcm[ind, j, k]

        ind = np.nonzero(choices == 3)[0]
        quat[ind, 0] = dcm[ind, 2, 1] - dcm[ind, 1, 2]
        quat[ind, 1] = dcm[ind, 0, 2] - dcm[ind, 2, 0]
        quat[ind, 2] = dcm[ind, 1, 0] - dcm[ind, 0, 1]
        quat[ind, 3] = 1 + decision_matrix[ind, -1]

        quat /= np.linalg.norm(quat, axis=1)[:, None]

        if is_single:
            return cls(quat[0], normalized=True)
        else:
            return cls(quat, normalized=True)

    @classmethod
    def from_rotvec(cls, rotvec):
        """Initialize class from rotation vector.

        A rotation vector is a 3 dimensional vector which is co-directional to
        the axis of rotaion and whose norm gives the angle of rotation (in
        radians).

        Parameters
        ----------
        rotvec : array_like, shape (N, 3) or (3,)
            A single vector or a stack of vectors, where `rot_vec[i]` gives
            the ith rotation vector.
        """
        is_single = False
        rotvec = np.asarray(rotvec, dtype=float)

        if rotvec.ndim not in [1, 2] or rotvec.shape[-1] != 3:
            raise ValueError("Expected `rot_vec` to have shape (3,) "
                             "or (N, 3), got {}".format(rotvec.shape))

        # If a single vector is given, convert it to a 2D 1 x 3 matrix but
        # set self._single to True so that we can return appropriate objects
        # in the `as_...` methods
        if rotvec.shape == (3,):
            rotvec = rotvec[None, :]
            is_single = True

        num_rotations = rotvec.shape[0]

        norms = np.linalg.norm(rotvec, axis=1)
        small_angle = (norms <= 1e-3)
        large_angle = ~small_angle

        scale = np.empty(num_rotations)
        # Use the Taylor expansion of sin(x/2) / x for small angles
        scale[small_angle] = (0.5 - norms[small_angle] ** 2 / 48 +
                              norms[small_angle] ** 4 / 3840)
        scale[large_angle] = (np.sin(norms[large_angle] / 2) /
                              norms[large_angle])

        quat = np.empty((num_rotations, 4))
        quat[:, :3] = scale[:, None] * rotvec
        quat[:, 3] = np.cos(norms / 2)

        if is_single:
            return cls(quat[0], normalized=True)
        else:
            return cls(quat, normalized=True)

    def as_rotvec(self):
        """Return the rotation vector representation of the Rotation.

        This function returns a numpy.ndarray of shape (3,) or (N, 3)
        depending on the input that was used to initialize the object.

        A rotation vector is a 3 dimensional vector which is co-directional to
        the axis of rotation and whose norm gives the angle of rotation (in
        radians).
        """
        quat = self._quat.copy()
        # w > 0 to ensure 0 <= angle <= pi
        quat[quat[:, 3] < 0] *= -1

        angle = 2 * np.arctan2(np.linalg.norm(quat[:, :3], axis=1), quat[:, 3])

        small_angle = (angle <= 1e-3)
        large_angle = ~small_angle

        num_rotations = quat.shape[0]
        scale = np.empty(num_rotations)
        # Use the Taylor expansion of x / sin(x/2) for small angles
        scale[small_angle] = (2 + angle[small_angle] ** 2 / 12 +
                              7 * angle[small_angle] ** 4 / 2880)
        scale[large_angle] = (angle[large_angle] /
                              np.sin(angle[large_angle] / 2))

        rotvec = scale[:, None] * quat[:, :3]

        if self._single:
            return rotvec[0]
        else:
            return rotvec

    @staticmethod
    def _make_dcm_from_angle(char, angle, intrinsic=False):
        sinx = np.sin(angle)
        cosx = np.cos(angle)

        axis = char.lower()
        if axis == 'z':
            dcm = np.array([
                [cosx, -sinx, 0],
                [sinx, cosx, 0],
                [0, 0, 1]
                ])
        elif axis == 'y':
            dcm = np.array([
                [cosx, 0, sinx],
                [0, 1, 0],
                [-sinx, 0, cosx]
                ])
        elif axis == 'x':
            dcm = np.array([
                [1, 0, 0],
                [0, cosx, -sinx],
                [0, sinx, cosx]
                ])

        return dcm.transpose() if intrinsic else dcm

    @classmethod
    def _make_dcm_from_euler(cls, axis_str, angle):
        extrinsic = recompile("^[xyz]{1,3}$")
        intrinsic = recompile("^[XYZ]{1,3}$")

        if len(axis_str) != angle.shape[0]:
            raise ValueError("Number of axes specified in {0} does not match "
                             "number of angles given in {1}".format(axis_str,
                                                                    angle))
        if ((extrinsic.match(axis_str) is None) and
                (intrinsic.match(axis_str) is None)):
                raise ValueError("Cannot allow mixing of intrinsic and "
                                 "extrinsic rotations in sequence {}".format(
                                    axis_str))

        dcm = np.eye(3)
        if extrinsic.match(axis_str) is not None:
            # Build dcm with pre-multiplication
            for ind, char in enumerate(axis_str):
                dcm = np.einsum('...ij,...jk->...ik',
                                cls._make_dcm_from_angle(char, angle[ind],
                                                         False), dcm)
        elif intrinsic.match(axis_str) is not None:
            # Build dcm with post multiplication
            for ind, char in enumerate(axis_str):
                dcm = np.einsum('...ij,...ik->...ik', dcm,
                                cls._make_dcm_from_angle(char, angle[ind],
                                                         True))
        return dcm

    @classmethod
    def from_euler(cls, seq, angle_mat, deg=False):
        """Initialize rotation from Euler angles.

        Parameters
        ----------
        seq : str or array of str
            Each str[i] (or str itself) must be a string of upto 3 characters
            belonging to the set {'x', 'y', 'z'} or {'X', 'Y', 'Z'}. Each
            lowercase character represents an extrinsic rotation around the
            corresponding axis and an uppercase character represents an
            intrinsic rotation. Extrinsic and intrinsic rotations cannot be
            mixed in one function call. Its length must match that of the
            `angles` parameter.
        angle_mat : array_like, shape ([1 or 2 or 3], ) or (N, 3)
            Euler angles specified in radians (`deg` is False) or degrees if
            parameter `deg` is True. Each `angles[i]` corresponds to an array
            of angles matching the number of axes specified.
        deg : boolean
            If True, then the given angles are taken to be in degrees
        """
        angle_mat = np.asarray(angle_mat, dtype=float)
        if deg:
            angle_mat = np.deg2rad(angle_mat)

        if type(seq) is str:
            # The single rotation case. For this case, we can have up to 3 axes
            if len(seq) != angle_mat.shape[0] or angle_mat.ndim != 1:
                raise ValueError("Invalid axis sequence {0} for angles "
                                 "specified {1}".format(seq, angle_mat))

            return cls.from_dcm(cls._make_dcm_from_euler(seq, angle_mat))

        # seq is a list of strings which we convert to numpy array
        seq = np.asarray(seq, dtype=str)

        if seq.shape[0] != angle_mat.shape[0]:
            raise ValueError("Number of axis sequences specified ({0}) does "
                             "match number of angle sequences "
                             "specified".format(seq.shape[0],
                                                angle_mat.shape[0]))

        if angle_mat.ndim != 2 or angle_mat.shape[-1] != 3:
            raise ValueError("For multiple rotations, expected 3 angles per "
                             "sequence, got {}".format(angle_mat.shape[-1]))

        num_rotations = seq.shape[0]
        dcm_set = np.empty((num_rotations, 3, 3))

        for rot_num, axes in enumerate(seq):
            dcm_set[rot_num] = cls._make_dcm_from_euler(axes,
                                                        angle_mat[rot_num])

        return cls.from_dcm(dcm_set)
