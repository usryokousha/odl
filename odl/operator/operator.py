﻿# Copyright 2014-2016 The ODL development group
#
# This file is part of ODL.
#
# ODL is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ODL is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ODL.  If not, see <http://www.gnu.org/licenses/>.

"""Abstract mathematical operators."""

# Imports for common Python 2/3 codebase
from __future__ import print_function, division, absolute_import
from future import standard_library
from future.utils import raise_from
standard_library.install_aliases()
from builtins import object, super

import inspect
from numbers import Number, Integral
import sys

from odl.set import (LinearSpace, LinearSpaceVector, UniversalSpace,
                     Set, UniversalSet, Field)


__all__ = ('Operator', 'OperatorComp', 'OperatorSum',
           'OperatorLeftScalarMult', 'OperatorRightScalarMult',
           'FunctionalLeftVectorMult',
           'OperatorLeftVectorMult', 'OperatorRightVectorMult',
           'OperatorPointwiseProduct',
           'OpTypeError', 'OpDomainError', 'OpRangeError',
           'OpNotImplementedError')


def _default_call_out_of_place(op, x, **kwargs):
    """Default out-of-place evaluation.

    Parameters
    ----------
    x : `domain` element
        An object in the operator domain. The operator is applied
        to it.

    Returns
    -------
    out : `range` element
        An object in the operator range. The result of an operator
        evaluation.
    """
    out = op.range.element()
    op._call_in_place(x, out, **kwargs)
    return out


def _default_call_in_place(op, x, out, **kwargs):
    """Default in-place evaluation using ``Operator._call()``.

    Parameters
    ----------
    x : `domain` element
        An object in the operator domain. The operator is applied
        to it.

    out : `range` element
        An object in the operator range. The result of an operator
        evaluation.

    Returns
    -------
    None
    """
    out.assign(op.range.element(op._call_out_of_place(x, **kwargs)))


def _signature_from_spec(func):
    """Return the signature of a python function as a string.

    Parameters
    ----------
    func : `function`
        Function whose signature to compile

    Returns
    -------
    sig : string
        Signature of the function
    """
    py3 = (sys.version_info.major > 2)
    if py3:
        spec = inspect.getfullargspec(func)
    else:
        spec = inspect.getargspec(func)

    posargs = spec.args
    defaults = spec.defaults if spec.defaults is not None else []
    varargs = spec.varargs
    kwargs = spec.varkw if py3 else spec.keywords
    deflen = 0 if defaults is None else len(defaults)
    nodeflen = 0 if posargs is None else len(posargs) - deflen

    args = ['{}'.format(arg) for arg in posargs[:nodeflen]]
    args += ['{}={}'.format(arg, dval)
             for arg, dval in zip(posargs[nodeflen:], defaults)]
    if varargs:
        args += ['*{}'.format(varargs)]
    if py3:
        kw_only = spec.kwonlyargs
        kw_only_defaults = spec.kwonlydefaults
        if kw_only and not varargs:
            args += ['*']
        args += ['{}={}'.format(arg, kw_only_defaults[arg])
                 for arg in kw_only]
    if kwargs:
        args += ['**{}'.format(kwargs)]

    argstr = ', '.join(args)

    return '{}({})'.format(func.__name__, argstr)


def _dispatch_call_args(cls=None, bound_call=None, unbound_call=None,
                        attr='_call'):
    """Check the arguments of ``_call()`` or similar for conformity.

    The ``_call()`` method of `Operator` is allowed to have the
    following signatures:

    Python 2 and 3:
        - ``_call(self, x)``
        - ``_call(self, vec, out)``
        - ``_call(self, x, out=None)``

    Python 3 only:
        - ``_call(self, x, *, out=None)`` (``out`` as keyword-only
          argument)

    For disambiguation, the instance name (the first argument) **must**
    be 'self'.

    The name of the ``out`` argument **must** be 'out', the second
    argument may have any name.

    Additional variable ``**kwargs`` and keyword-only arguments
    (Python 3 only) are also allowed.

    Not allowed:
        - ``_call(self)`` -- No arguments except instance:
        - ``_call(x)`` -- 'self' missing, i.e. ``@staticmethod``
        - ``_call(cls, x)``  -- 'self' missing, i.e. ``@classmethod``
        - ``_call(self, out, x)`` -- ``out`` as second argument
        - ``_call(self, *x)`` -- Variable arguments
        - ``_call(self, x, y, out=None)`` -- more positional arguments
        - ``_call(self, x, out=False)`` -- default other than None for
          ``out``

    In particular, static or class methods are not allowed.

    Parameters
    ----------
    cls : `class`, optional
        The ``_call()`` method of this class is checked. If omitted,
        provide ``unbound_call`` instead to check directly.
    bound_call: `callable`, optional
        Check this bound method instead of ``cls``
    unbound_call: `callable`, optional
        Check this unbound function instead of ``cls``
    attr : string, optional
        Check this attribute instead of ``_call``, e.g. ``__call__``

    Returns
    -------
    has_out : bool
        Whether the call has an ``out`` argument
    out_is_optional : bool
        Whether the ``out`` argument is optional
    spec : `inspect.ArgSpec` or `inspect.FullArgSpec`
        Argument specification of the checked call function

    Raises
    ------
    ValueError
        if the signature of the function is malformed
    """
    py3 = (sys.version_info.major > 2)

    specs = ['_call(self, x[, **kwargs])',
             '_call(self, x, out[, **kwargs])',
             '_call(self, x, out=None[, **kwargs])']

    if py3:
        specs += ['_call(self, x, *, out=None[, **kwargs])']

    spec_msg = "\nPossible signatures are ('[, **kwargs]' means optional):\n\n"
    spec_msg += '\n'.join(specs)
    spec_msg += '\n\nStatic or class methods are not allowed.'

    if sum(arg is not None for arg in (cls, bound_call, unbound_call)) != 1:
        raise ValueError('exactly one object to check must be given')

    if cls is not None:
        # Get the actual implementation, including ancestors
        for parent in cls.mro():
            call = parent.__dict__.get(attr, None)
            if call is not None:
                break
        # Static and class methods are not allowed
        if isinstance(call, staticmethod):
            raise TypeError("'{}.{}' is a static method. "
                            "".format(cls.__name__, attr) + spec_msg)
        elif isinstance(call, classmethod):
            raise TypeError("'{}.{}' is a class method. "
                            "".format(cls.__name__, attr) + spec_msg)

    elif bound_call is not None:
        call = bound_call
        if not inspect.ismethod(call):
            raise TypeError('{} is not a bound method'.format(call))
    else:
        call = unbound_call

    if py3:
        # support kw-only args and annotations
        spec = inspect.getfullargspec(call)
        kw_only = spec.kwonlyargs
        kw_only_defaults = spec.kwonlydefaults
    else:
        spec = inspect.getargspec(call)
        kw_only = ()
        kw_only_defaults = {}

    signature = _signature_from_spec(call)

    pos_args = spec.args
    if unbound_call is not None:
        # Add 'self' to positional arg list to satisfy the checker
        pos_args.insert(0, 'self')

    pos_defaults = spec.defaults
    varargs = spec.varargs

    # Variable args are not allowed
    if varargs is not None:
        raise ValueError("bad signature '{}': variable arguments not allowed"
                         "".format(signature) + spec_msg)

    if len(pos_args) not in (2, 3):
        raise ValueError("bad signature '{}'".format(signature) + spec_msg)

    true_pos_args = pos_args[1:]
    if len(true_pos_args) == 1:  # 'out' kw-only
        if 'out' in true_pos_args:  # 'out' positional and 'x' kw-only -> no
            raise ValueError("bad signature '{}': `out` cannot be the only "
                             "positional argument"
                             "".format(signature) + spec_msg)
        else:
            if 'out' not in kw_only:
                has_out = out_optional = False
            elif kw_only_defaults['out'] is not None:
                raise ValueError(
                    "bad signature '{}': `out` can only default to "
                    "`None`, got '{}'"
                    "".format(signature, kw_only_defaults['out']) +
                    spec_msg)
            else:
                has_out = True
                out_optional = True

    elif len(true_pos_args) == 2:  # Both args positional
        if true_pos_args[0] == 'out':  # out must come second
            py3_txt = ' or keyword-only. ' if py3 else '. '
            raise ValueError("bad signature '{}': `out` can only be the "
                             "second positional argument".format(signature) +
                             py3_txt + spec_msg)
        elif true_pos_args[1] != 'out':  # 'out' must be 'out'
            raise ValueError("bad signature '{}': output parameter must "
                             "be called 'out', got '{}'"
                             "".format(signature, true_pos_args[1]) +
                             spec_msg)
        else:
            has_out = True
            out_optional = bool(pos_defaults)
            if pos_defaults and pos_defaults[-1] is not None:
                raise ValueError("bad signature '{}': `out` can only "
                                 "default to `None`, got '{}'"
                                 "".format(signature, pos_defaults[-1]) +
                                 spec_msg)

    else:  # Too many positional args
        raise ValueError("bad signature '{}': too many positional arguments"
                         " ".format(signature) + spec_msg)

    return has_out, out_optional, spec


class Operator(object):

    """Abstract mathematical operator.

    An operator is a mapping

        :math:`\mathcal{A}: \mathcal{X} \\to \mathcal{Y}`

    between sets :math:`\mathcal{X}` (domain) and :math:`\mathcal{Y}`
    (range). The evaluation of :math:`\mathcal{A}` at an element
    :math:`x \\in \mathcal{X}` is denoted by :math:`\mathcal{A}(x)`
    and produces an element in :math:`\mathcal{Y}`:

        :math:`y = \mathcal{A}(x) \\in \mathcal{Y}`.

    Programmatically, these properties are reflected in the `Operator`
    class described in the following.

    **Abstract attributes and methods**

    `Operator` is an **abstract** class, i.e. it can only be
    subclassed, not used directly.

    Any subclass of `Operator` must have the following
    attributes:

    ``domain`` : `Set`
        The set of elements this operator can be applied to

    ``range`` : `Set`
        The set this operator maps to

    It is **highly** recommended to call
    ``super().__init__(domain, range)`` (Note: add
    ``from builtins import super`` in Python 2) in the ``__init__()``
    method of any subclass, where ``domain`` and ``range`` are the arguments
    specifying domain and range of the new operator. In that case, the
    attributes `Operator.domain` and `Operator.range` are automatically
    provided by the parent class `Operator`.

    In addition, any subclass **must** implement the private method
    `Operator._call()`. It signature determines how it is interpreted:


    **In-place-only evaluation:** ``_call(self, x, out[, **kwargs])``

    In-place evaluation means that the operator is applied, and the
    result is written to an existing element ``out`` provided,
    i.e.

        ``_call(self, x, out)  <==>  out <-- operator(x)``

    **Parameters:**

    x : `Operator.domain` element
        An object in the operator domain to which the operator is
        applied

    out : `Operator.range` element
        An object in the operator range to which the result of the
        operator evaluation is written.

    **Returns:**

    None (return value is ignored)


    **Out-of-place-only evaluation:** ``_call(self, x[, **kwargs])``

    Out-of-place evaluation means that the operator is applied,
    and the result is written to a **new** element which is returned.
    In this case, a subclass has to implement the method

        ``_call(self, x)  <==>  operator(x)``

    **Parameters:**

    x : `Operator.domain` element
        An object in the operator domain to which the operator is
        applied

    **Returns:**

    out : `Operator.range` `element-like`
        An object in the operator range holding the result of the
        operator evaluation


    **Dual-use evaluation:** ``_call(self, x, out=None[, **kwargs])``

    Evaluate in-place if ``out`` is given, otherwise out-of-place.

    **Parameters:**

    x : `Operator.domain` element
        An object in the operator domain to which the operator is
        applied

    out : `Operator.range` element, optional
        An object in the operator range to which the result of the
        operator evaluation is written

    **Returns:**

    None (return value is ignored)


    Notes
    -----
    - If `Operator._call` is implemented in-place-only or
      out-of-place-only and the `Operator.range` is a `LinearSpace`,
      a default implementation of the respective other is provided.

    - `Operator._call` is allowed to have keyword-only arguments (Python
      3 only).

    - The term "element-like" means that an object must be convertible
      to an element by the ``domain.element()`` method.
    """

    def __new__(cls, *args, **kwargs):
        """Create a new instance."""
        call_has_out, call_out_optional, _ = _dispatch_call_args(cls)
        cls._call_has_out = call_has_out
        cls._call_out_optional = call_out_optional
        if not call_has_out:
            # Out-of-place _call
            cls._call_in_place = _default_call_in_place
            cls._call_out_of_place = cls._call
        elif call_out_optional:
            # Dual-use _call
            cls._call_in_place = cls._call_out_of_place = cls._call
        else:
            # In-place-only _call
            cls._call_in_place = cls._call
            cls._call_out_of_place = _default_call_out_of_place

        return object.__new__(cls)

    def __init__(self, domain, range, linear=False):
        """Initialize a new instance.

        Parameters
        ----------
        domain : `Set`
            The domain of this operator, i.e., the set of elements to
            which this operator can be applied
        range : `Set`
            The range of this operator, i.e., the set this operator
            maps to
        linear : bool
            If ``True``, the operator is considered as linear. In this
            case, ``domain`` and ``range`` have to be instances of
            `LinearSpace`, or `Field`.
        """
        if not isinstance(domain, Set):
            raise TypeError('`domain` {!r} is not a `Set` instance'
                            ''.format(domain))
        if not isinstance(range, Set):
            raise TypeError('`range` {!r} is not a `Set` instance'
                            ''.format(range))

        self.__domain = domain
        self.__range = range
        self.__is_linear = bool(linear)

        # Cache for efficiency since this is done in each call.
        self.__is_functional = isinstance(range, Field)

        # Mandatory out makes no sense for functionals.
        # However, we need to allow optional out to support vectorized
        # functions (which are functionals in the duck-typing sense).
        if (self.is_functional and self._call_has_out and
                not self._call_out_optional):
            raise ValueError('mandatory `out` parameter not allowed for '
                             'functionals')

        if self.is_linear:
            if not isinstance(domain, (LinearSpace, Field)):
                raise TypeError('`domain` {!r} not a `LinearSpace` or `Field` '
                                'instance'.format(domain))
            if not isinstance(range, (LinearSpace, Field)):
                raise TypeError('`range` {!r} not a `LinearSpace` or `Field` '
                                'instance'.format(range))

    def _call(self, x, out=None, **kwargs):
        """Implementation of the operator evaluation.

        This method is the private backend for the evaluation of an
        operator. It needs to match certain signature conventions,
        and its implementation type is inferred from its signature.

        The following signatures are allowed:

        Python 2 and 3:
            - ``_call(self, x)``  -->  out-of-place evaluation
            - ``_call(self, vec, out)``  -->  in-place evaluation
            - ``_call(self, x, out=None)``   --> both

        Python 3 only:
            - ``_call(self, x, *, out=None)`` (``out`` as keyword-only
              argument)  --> both

        For disambiguation, the instance name (the first argument) **must**
        be 'self'.

        The name of the ``out`` argument **must** be 'out', the second
        argument may have any name.

        Additional variable ``**kwargs`` and keyword-only arguments
        (Python 3 only) are also allowed.

        Notes
        -----
        Some general advice on how to implement operator evaluation:

        - If you just write a quick implementation or are not too
          worried about efficiency, it may be easiest to write the
          evaluation *out-of-place*.
        - We recommend advanced and performance-aware users to implement
          the *in-place* pattern if the wrapped code supports it.
          In-place evaluation is usually significantly faster since it
          avoids the allocation of new memory and a copy compared to
          out-of-place evaluation.
        - If there is a significant performance gain from implementing
          an out-of-place method separately, use the pattern for both
          (``out`` optional) and decide according to the given ``out``
          parameter which one to use.
        - If your evaluation code does not support in-place evaluation,
          use the out-of-place pattern.

        Note that the public call pattern ``op()`` using ``op.__call__``
        provides a default implementation of the underlying in-place or
        out-of-place call even if you choose the respective other
        pattern.

        See the `documentation
        <https://odl.readthedocs.io/guide/in_depth/operator_guide.html>`_
        for more info on in-place vs. out-of-place evaluation.

        Parameters
        ----------
        x : `domain` `element-like`
            Element to which the operator is applied
        out : `range` element, optional
            Element to which the result is written

        Returns
        -------
        out : `range` `element-like`
            Result of the evaluation. If ``out`` was provided, the
            returned object is a reference to it.
        """
        raise NotImplementedError('this operator {!r} does not implement '
                                  '`_call`. See `Operator._call` for '
                                  'instructions on how to do this.'
                                  ''.format(self))

    @property
    def domain(self):
        """Set of objects on which this operator can be evaluated."""
        return self.__domain

    @property
    def range(self):
        """Set in which the result of an evaluation of this operator lies."""
        return self.__range

    @property
    def is_linear(self):
        """``True`` if this operator is linear."""
        return self.__is_linear

    @property
    def is_functional(self):
        """``True`` if this operator's range is a `Field`."""
        return self.__is_functional

    @property
    def adjoint(self):
        """Adjoint of this operator (abstract).

        Raises
        ------
        OpNotImplementedError
            Since the adjoint cannot be default implemented.
        """
        raise OpNotImplementedError('adjoint not implemented '
                                    'for operator {!r}'
                                    ''.format(self))

    def derivative(self, point):
        """Return the operator derivative at ``point``.

        Raises
        ------
        OpNotImplementedError
            If the operator is not linear, the derivative cannot be
            default implemented.
        """
        if self.is_linear:
            return self
        else:
            raise OpNotImplementedError('derivative not implemented '
                                        'for operator {!r}'
                                        ''.format(self))

    @property
    def inverse(self):
        """Return the operator inverse.

        Raises
        ------
        OpNotImplementedError
            Since the inverse cannot be default implemented.
        """
        raise OpNotImplementedError('inverse not implemented for operator {!r}'
                                    ''.format(self))

    def __call__(self, x, out=None, **kwargs):
        """Return ``self(x[, out, **kwargs])``.

        Implementation of the call pattern ``op(x)`` with the private
        ``_call()`` method and added error checking.

        Parameters
        ----------
        x : `domain` `element-like`
            An object which can be converted into an element of this
            operator's domain with the ``self.domain.element`` method.
            The operator is applied to this object, which is treated
            as immutable, hence it is not modified during evaluation.
        out : `range` element, optional
            An object in the operator range to which the result of the
            operator evaluation is written. The result is independent
            of the initial state of this object.
        kwargs :
            Passed on to the underlying implementation in `_call`.

        Returns
        -------
        out : `range` element
            Result of the operator evaluation. If ``out`` was provided,
            the returned object is a reference to it.

        Examples
        --------
        >>> import odl
        >>> rn = odl.rn(3)
        >>> op = odl.ScalingOperator(rn, 2.0)
        >>> x = rn.element([1, 2, 3])

        Out-of-place evaluation:

        >>> op(x)
        rn(3).element([2.0, 4.0, 6.0])

        In-place evaluation:

        >>> y = rn.element()
        >>> op(x, out=y)
        rn(3).element([2.0, 4.0, 6.0])
        >>> y
        rn(3).element([2.0, 4.0, 6.0])

        See Also
        --------
        _call : Implementation of the method
        """
        if x not in self.domain:
            try:
                x = self.domain.element(x)
            except (TypeError, ValueError) as err:
                raise_from(OpDomainError(
                    'unable to cast {!r} to an element of '
                    'the domain {!r}'.format(x, self.domain)), err)

        if out is not None:  # In-place evaluation
            if out not in self.range:
                raise OpRangeError('`out` {!r} not an element of the range '
                                   '{!r} of {!r}'
                                   ''.format(out, self.range, self))

            if self.is_functional:
                raise TypeError('`out` parameter cannot be used '
                                'when range is a field')

            self._call_in_place(x, out=out, **kwargs)

        else:  # Out-of-place evaluation
            out = self._call_out_of_place(x, **kwargs)

            if out not in self.range:
                try:
                    out = self.range.element(out)
                except (TypeError, ValueError) as err:
                    new_exc = OpRangeError(
                        'unable to cast {!r} to an element of '
                        'the range {!r}'.format(out, self.range))
                    raise_from(new_exc, err)
        return out

    def __add__(self, other):
        """Return ``self + other``."""
        return OperatorSum(self, other)

    def __sub__(self, other):
        """Return ``self - other``."""
        return OperatorSum(self, -1 * other)

    def __mul__(self, other):
        """Return ``self * other``.

        If ``other`` is an operator, this corresponds to
        operator composition:

            ``left * right <==> (x --> left(right(x))``

        If ``other`` is a scalar, this corresponds to right
        multiplication of scalars with operators:

            ``op * scalar <==> (x --> op(scalar * x))``

        If ``other`` is a vector, this corresponds to right
        multiplication of vectors with operators:

            ``op * vector <==> (x --> op(vector * x))``

        Note that left and right multiplications are generally
        different.

        Parameters
        ----------
        other : `Operator`, `LinearSpaceVector` or scalar
            `Operator`:
                The `Operator.domain` of ``other`` must match this
                operator's `Operator.range`.

            `LinearSpaceVector`:
                ``other`` must be an element of this operator's
                `Operator.domain`.

            scalar:
                The `Operator.domain` of this operator must be a
                `LinearSpace` and ``other`` must be an
                element of the ``field`` of this operator's
                `Operator.domain`.

        Returns
        -------
        mul : `Operator`
            The multiplication operator.

            If ``other`` is an operator, ``mul`` is an
            `OperatorComp`.

            If ``other`` is a scalar, ``mul`` is an
            `OperatorRightScalarMult`.

            If ``other`` is a vector, ``mul`` is an
            `OperatorRightVectorMult`.

        Examples
        --------
        >>> import odl
        >>> rn = odl.rn(3)
        >>> op = odl.IdentityOperator(rn)
        >>> x = rn.element([1, 2, 3])
        >>> op(x)
        rn(3).element([1.0, 2.0, 3.0])
        >>> Scaled = op * 3
        >>> Scaled(x)
        rn(3).element([3.0, 6.0, 9.0])
        """
        if isinstance(other, Operator):
            return OperatorComp(self, other)
        elif isinstance(other, Number):
            # Left multiplication is more efficient, so we can use this in the
            # case of linear operator.
            if self.is_linear:
                return OperatorLeftScalarMult(self, other)
            else:
                return OperatorRightScalarMult(self, other)
        elif isinstance(other, LinearSpaceVector) and other in self.domain:
            return OperatorRightVectorMult(self, other.copy())
        else:
            return NotImplemented

    def __matmul__(self, other):
        """Return ``self @ other``.

        See `Operator.__mul__`
        """
        return self.__mul__(other)

    def __rmul__(self, other):
        """Return ``other * self``.

        If ``other`` is an `Operator`, this corresponds to
        operator composition:

        ``left * right <==> (x --> left(right(x)))``

        If ``other`` is a scalar, this corresponds to left
        multiplication of scalars with operators:

        ``scalar * op <==> (x --> scalar * op(x))``

        If ``other`` is a vector, this corresponds to left
        multiplication of vector with operators:

        ``vector * op <==> (x --> vector * op(x))``

        Note that left and right multiplications are generally
        different.

        Parameters
        ----------
        other : {`Operator`, `LinearSpaceVector`, scalar}
            `Operator`:
                The `Operator.range` of ``other`` must match this
                operator's `Operator.domain`

            `LinearSpaceVector`:
                ``other`` must be an element of `Operator.range`.

            scalar:
                `Operator.range` must be a
                `LinearSpace` and ``other`` must be an
                element of ``self.range.field``.

        Returns
        -------
        mul : `Operator`
            The multiplication operator.

            If ``other`` is an operator, ``mul`` is an
            `OperatorComp`.

            If ``other`` is a scalar, ``mul`` is an
            `OperatorLeftScalarMult`.

            If ``other`` is a vector, ``mul`` is an
            `OperatorLeftVectorMult`.

        Examples
        --------
        >>> import odl
        >>> rn = odl.rn(3)
        >>> op = odl.IdentityOperator(rn)
        >>> x = rn.element([1, 2, 3])
        >>> op(x)
        rn(3).element([1.0, 2.0, 3.0])
        >>> Scaled = 3 * op
        >>> Scaled(x)
        rn(3).element([3.0, 6.0, 9.0])
        """
        if isinstance(other, Operator):
            return OperatorComp(other, self)
        elif isinstance(other, Number):
            return OperatorLeftScalarMult(self, other)
        elif other in self.range:
            return OperatorLeftVectorMult(self, other.copy())
        elif (isinstance(other, LinearSpaceVector) and
              other.space.field == self.range):
            return FunctionalLeftVectorMult(self, other.copy())
        else:
            return NotImplemented

    def __rmatmul__(self, other):
        """Return ``other @ op``.

        See `Operator.__rmul__`
        """
        return self.__rmul__(other)

    def __pow__(self, n):
        """Return ``op**s``.

        This corresponds to the power of an operator:

        ``op ** 1 <==> (x --> op(x))``
        ``op ** 2 <==> (x --> op(op(x)))``
        ``op ** 3 <==> (x --> op(op(op(x))))``
        ...

        Parameters
        ----------
        n : positive int
            The power the operator should be taken to.

        Returns
        -------
        pow : `Operator`
            The power of this operator. If ``n == 1``, ``pow`` is
            this operator, for ``n > 1``, a `OperatorComp`

        Examples
        --------
        >>> import odl
        >>> rn = odl.rn(3)
        >>> op = odl.ScalingOperator(rn, 3)
        >>> x = rn.element([1, 2, 3])
        >>> op(x)
        rn(3).element([3.0, 6.0, 9.0])
        >>> squared = op**2
        >>> squared(x)
        rn(3).element([9.0, 18.0, 27.0])
        >>> squared = op**3
        >>> squared(x)
        rn(3).element([27.0, 54.0, 81.0])
        """
        if isinstance(n, Integral) and n > 0:
            op = self
            while n > 1:
                op = OperatorComp(self, op)
                n -= 1
            return op
        else:
            return NotImplemented

    def __truediv__(self, other):
        """Return ``self / other``.

        If ``other`` is a scalar, this corresponds to right
        division of operators with scalars:

        ``op / scalar <==> (x --> op(x / scalar))``

        Parameters
        ----------
        other : scalar
            If `Operator.range` is a `LinearSpace`, ``scalar`` must be
            an element of the ``field`` of this operator's range.

        Returns
        -------
        rmul : `OperatorRightScalarMult`
            The 'divided' operator.

        Examples
        --------
        >>> import odl
        >>> rn = odl.rn(3)
        >>> op = odl.IdentityOperator(rn)
        >>> x = rn.element([3, 6, 9])
        >>> op(x)
        rn(3).element([3.0, 6.0, 9.0])
        >>> Scaled = op / 3.0
        >>> Scaled(x)
        rn(3).element([1.0, 2.0, 3.0])
        """
        if isinstance(other, Number):
            return self * (1.0 / other)
        else:
            return NotImplemented

    __div__ = __truediv__

    def __neg__(self):
        """Return ``-self``."""
        return -1 * self

    def __pos__(self):
        """Return ``+op``.

        The operator itself.
        """
        return self

    def __repr__(self):
        """Return ``repr(self)``.

        The default `repr` implementation. Should be overridden by
        subclasses.
        """
        return '{}: {!r} -> {!r}'.format(self.__class__.__name__, self.domain,
                                         self.range)

    def __str__(self):
        """Return ``str(self)``.

        The default string implementation. Should be overridden by
        subclasses.
        """
        return self.__class__.__name__

    # Give a `Operator` a higher priority than any NumPy array type. This
    # forces the usage of `__op__` of `Operator` if the other operand
    # is a NumPy object (applies also to scalars!).
    # Set higher than LinearSpaceVector.__array_priority__ to handle mult with
    # vector properly
    __array_priority__ = 2000000.0


class OperatorSum(Operator):

    """Expression type for the sum of operators.

    ``OperatorSum(left, right) <==> (x --> left(x) + right(x))``

    The sum is only well-defined for `Operator` instances where
    `Operator.range` is a `LinearSpace`.

    """

    def __init__(self, left, right, tmp_ran=None, tmp_dom=None):
        """Initialize a new instance.

        Parameters
        ----------
        left : `Operator`
            First summand. Its `Operator.range` must be a `LinearSpace` or
            `Field`.
        right : `Operator`
            Second summand. Must have the same `Operator.domain` and
            `Operator.range` as ``left``.
        tmp_ran : `Operator.range` element, optional
            Used to avoid the creation of a temporary when applying the
            operator.
        tmp_dom : `Operator.domain` element, optional
            Used to avoid the creation of a temporary when applying the
            operator adjoint.
        """
        if left.range != right.range:
            raise TypeError('operator ranges {!r} and {!r} do not match'
                            ''.format(left.range, right.range))
        if not isinstance(left.range, (LinearSpace, Field)):
            raise TypeError('`left.range` {!r} not a `LinearSpace` or `Field` '
                            'instance'.format(left.range))
        if left.domain != right.domain:
            raise TypeError('operator domains {!r} and {!r} do not match'
                            ''.format(left.domain, right.domain))

        if tmp_ran is not None and tmp_ran not in left.range:
            raise TypeError('`tmp_ran` {!r} not an element of the operator '
                            'range {!r}'.format(tmp_ran, left.range))
        if tmp_dom is not None and tmp_dom not in left.domain:
            raise TypeError('`tmp_dom` {!r} not an element of the operator '
                            'domain {!r}'.format(tmp_dom, left.domain))

        super().__init__(left.domain, left.range,
                         linear=left.is_linear and right.is_linear)
        self.__left = left
        self.__right = right
        self.__tmp_ran = tmp_ran
        self.__tmp_dom = tmp_dom

    @property
    def left(self):
        """The left/first part of this sum."""
        return self.__left

    @property
    def right(self):
        """The left/second part of this sum."""
        return self.__right

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``.

        Examples
        --------
        >>> import odl
        >>> r3 = odl.rn(3)
        >>> op = odl.IdentityOperator(r3)
        >>> x = r3.element([1, 2, 3])
        >>> out = r3.element()
        >>> OperatorSum(op, op)(x, out)  # In-place, returns out
        rn(3).element([2.0, 4.0, 6.0])
        >>> out
        rn(3).element([2.0, 4.0, 6.0])
        >>> OperatorSum(op, op)(x)
        rn(3).element([2.0, 4.0, 6.0])
        """
        if out is None:
            return self.left(x) + self.right(x)
        else:
            tmp = (self.__tmp_ran if self.__tmp_ran is not None
                   else self.range.element())
            self.left(x, out=out)
            self.right(x, out=tmp)
            out += tmp

    def derivative(self, x):
        """Return the operator derivative at ``x``.

        The derivative of a sum of two operators is equal to the sum of
        the derivatives.

        Parameters
        ----------
        x : `domain` `element-like`
            Evaluation point of the derivative
        """
        return OperatorSum(self.left.derivative(x), self.right.derivative(x),
                           self.__tmp_dom, self.__tmp_ran)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator sum is the sum of the operator
        adjoints:

        ``OperatorSum(left, right).adjoint ==
        OperatorSum(left.adjoint, right.adjoint)``

        Returns
        -------
        adjoint : `OperatorSum`

        Raises
        ------
        OpNotImplementedError
            If either of the underlying operators are non-linear.
        """
        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        return OperatorSum(self.left.adjoint, self.right.adjoint,
                           self.__tmp_dom, self.__tmp_ran)

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.left, self.right)

    def __str__(self):
        """Return ``str(self)``."""
        return '({} + {})'.format(self.left, self.right)


class OperatorComp(Operator):

    """Expression type for the composition of operators.

    ``OperatorComp(left, right) <==> (x --> left(right(x)))``

    The composition is only well-defined if
    ``left.domain == right.range``.
    """

    def __init__(self, left, right, tmp=None):
        """Initialize a new `OperatorComp` instance.

        Parameters
        ----------
        left : `Operator`
            The left ("outer") operator
        right : `Operator`
            The right ("inner") operator. Its range must coincide with the
            domain of ``left``.
        tmp : element of the range of ``right``, optional
            Used to avoid the creation of a temporary when applying the
            operator.
        """
        if right.range != left.domain:
            raise TypeError('`range` {!r} of the right operator {!r} not equal'
                            ' to the domain {!r} of the left operator {!r}'
                            ''.format(right.range, right,
                                      left.domain, left))

        if tmp is not None and tmp not in left.domain:
            raise TypeError('`tmp` {!r} not an element of the left '
                            'operator domain {!r}'.format(tmp, left.domain))

        super().__init__(right.domain, left.range,
                         linear=left.is_linear and right.is_linear)
        self.__left = left
        self.__right = right
        self.__tmp = tmp

    @property
    def left(self):
        """The left/first part of this composition."""
        return self.__left

    @property
    def right(self):
        """The left/second part of this composition."""
        return self.__right

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``."""
        if out is None:
            return self.left(self.right(x))
        else:
            tmp = (self.__tmp if self.__tmp is not None
                   else self.right.range.element())
            self.right(x, out=tmp)
            return self.left(tmp, out=out)

    @property
    def inverse(self):
        """Inverse of this operator.

        The inverse of the operator composition is the composition of
        the inverses in reverse order:

        ``OperatorComp(left, right).inverse ==``
        ``OperatorComp(right.inverse, left.inverse)``
        """
        return OperatorComp(self.right.inverse, self.left.inverse,
                            self.__tmp)

    def derivative(self, x):
        """Return the operator derivative.

        The derivative of the operator composition follows the chain
        rule:

        ``OperatorComp(left, right).derivative(x) ==
        OperatorComp(left.derivative(right(x)), right.derivative(x))``

        Parameters
        ----------
        x : `domain` `element-like`
            Evaluation point of the derivative. Needs to be usable as
            input for the ``right`` operator.
        """
        left_deriv = self.left.derivative(self.right(x))
        right_deriv = self.right.derivative(x)

        return OperatorComp(left_deriv, right_deriv,
                            self.__tmp)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator composition is the composition of
        the operator adjoints in reverse order:

        ``OperatorComp(left, right).adjoint ==
        OperatorComp(right.adjoint, left.adjoint)``

        Returns
        -------
        adjoint : `OperatorComp`

        Raises
        ------
        OpNotImplementedError
            If any of the underlying operators are non-linear.
        """
        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        return OperatorComp(self.right.adjoint, self.left.adjoint,
                            self.__tmp)

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.left, self.right)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} o {}'.format(self.left, self.right)


class OperatorPointwiseProduct(Operator):

    """Expression type for the pointwise operator mulitplication.

    ``OperatorPointwiseProduct(left, right) <==> (x --> left(x) * right(x))``
    """

    def __init__(self, left, right):
        """Initialize a new instance.

        Parameters
        ----------
        left : `Operator`
            The first factor
        right : `Operator`
            The second factor. Must have the same domain and range as
            ``left``.
        """
        if left.range != right.range:
            raise TypeError('operator ranges {!r} and {!r} do not match'
                            ''.format(left.range, right.range))
        if not isinstance(left.range, (LinearSpace, Field)):
            raise TypeError('range {!r} not a `LinearSpace` or `Field` '
                            'instance'.format(left.range))
        if left.domain != right.domain:
            raise TypeError('operator domains {!r} and {!r} do not match'
                            ''.format(left.domain, right.domain))

        super().__init__(left.domain, left.range, linear=False)
        self.__left = left
        self.__right = right

    @property
    def left(self):
        """The left/first part of this multiplication."""
        return self.__left

    @property
    def right(self):
        """The left/second part of this multiplication."""
        return self.__right

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``."""
        if out is None:
            return self.left(x) * self.right(x)
        else:
            tmp = self.right.range.element()
            self.left(x, out=out)
            self.right(x, out=tmp)
            out *= tmp

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.left, self.right)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.left, self.right)


class OperatorLeftScalarMult(Operator):

    """Expression type for the operator left scalar multiplication.

    ``OperatorLeftScalarMult(op, scalar) <==> (x --> scalar * op(x))``

    The scalar multiplication is well-defined only if ``op.range`` is
    a `LinearSpace`.
    """

    def __init__(self, operator, scalar):
        """Initialize a new `OperatorLeftScalarMult` instance.

        Parameters
        ----------
        operator : `Operator`
            Operator in the scalar multiplication. Its `range` must be
            a `LinearSpace` or `Field`.
        scalar : ``operator.range.field`` element
            A real or complex number, depending on the field of
            the range.
        """
        if not isinstance(operator.range, (LinearSpace, Field)):
            raise TypeError('range {!r} not a `LinearSpace` or `Field` '
                            'instance'.format(operator.range))

        if scalar not in operator.range.field:
            raise TypeError('`scalar` {!r} not in the field {!r} of the '
                            'operator range {!r}'
                            ''.format(scalar,
                                      operator.range.field,
                                      operator.range))

        super().__init__(operator.domain, operator.range,
                         linear=operator.is_linear)
        self.__operator = operator
        self.__scalar = scalar

    @property
    def operator(self):
        """The operator part of this multiplication."""
        return self.__operator

    @property
    def scalar(self):
        """The scalar part of this multiplication."""
        return self.__scalar

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``.

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorLeftScalarMult(operator, 3)
        >>> left_mul_op([1, 2, 3])
        rn(3).element([3.0, 6.0, 9.0])
        """
        if out is None:
            return self.scalar * self.operator(x)
        else:
            self.operator(x, out=out)
            out *= self.scalar

    def __rmul__(self, other):
        """Implement ``other * self``.

        Optimization for repeated multiplications.
        """

        if other in self.range.field:
            return OperatorLeftScalarMult(self.operator, self.scalar * other)
        else:
            return super().__rmul__(other)

    @property
    def inverse(self):
        """Inverse of this operator.

        The inverse of ``scalar * op`` is given by
        ``op.inverse * 1/scalar`` if ``scalar != 0``. If ``scalar == 0``,
        the inverse is not defined.

        ``OperatorLeftScalarMult(op, scalar).inverse <==>``
        ``OperatorRightScalarMult(op.inverse, 1.0/scalar)``

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorLeftScalarMult(operator, 3)
        >>> left_mul_op.inverse([3, 3, 3])
        rn(3).element([1.0, 1.0, 1.0])
        """
        if self.scalar == 0.0:
            raise ZeroDivisionError('{} not invertible'.format(self))

        return self.operator.inverse * (1.0 / self.scalar)

    def derivative(self, x):
        """Return the derivative at ``x``.

        Left scalar multiplication and derivative are commutative:

        ``OperatorLeftScalarMult(op, scalar).derivative(x) <==>``
        ``OperatorLeftScalarMult(op.derivative(x), scalar)``

        Parameters
        ----------
        x : `domain` `element-like`
            Evaluation point of the derivative

        Returns
        -------
        derivative : `OperatorLeftScalarMult`

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.ResidualOperator(odl.IdentityOperator(space),
        ...                                 [1, 1, 1])
        >>> left_mul_op = OperatorLeftScalarMult(operator, 3)
        >>> derivative = left_mul_op.derivative([0, 0, 0])
        >>> derivative([1, 1, 1])
        rn(3).element([3.0, 3.0, 3.0])
        """
        if self.is_linear:
            return self
        else:
            return self.scalar * self.operator.derivative(x)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator scalar multiplication is the
        scalar multiplication of the operator adjoint:

        ``OperatorLeftScalarMult(op, scalar).adjoint ==``
        ``OperatorLeftScalarMult(op.adjoint, scalar)``

        Raises
        ------
        OpNotImplementedError
            If the underlying operator is non-linear.

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorLeftScalarMult(operator, 3)
        >>> left_mul_op.adjoint([1, 2, 3])
        rn(3).element([3.0, 6.0, 9.0])
        """

        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        return self.scalar.conjugate() * self.operator.adjoint

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.operator, self.scalar)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.scalar, self.operator)


class OperatorRightScalarMult(Operator):

    """Expression type for the operator right scalar multiplication.

    ``OperatorRightScalarMult(op, scalar) <==> (x --> op(scalar * x))``

    The scalar multiplication is well-defined only if ``op.domain`` is
    a `LinearSpace`.
    """

    def __init__(self, operator, scalar, tmp=None):
        """Initialize a new `OperatorLeftScalarMult` instance.

        Parameters
        ----------
        operator : `Operator`
            Operator in the scalar multiplication. Its `domain` must
            be a `LinearSpace` or `Field`.
        scalar : ``operator.range.field`` element
            A real or complex number, depending on the field of
            the operator domain.
        tmp : `domain` element, optional
            Used to avoid the creation of a temporary when applying the
            operator.
        """
        if not isinstance(operator.domain, (LinearSpace, Field)):
            raise TypeError('domain {!r} not a `LinearSpace` or `Field` '
                            'instance'.format(operator.domain))

        if scalar not in operator.domain.field:
            raise TypeError('`scalar` {!r} not in the field {!r} of the '
                            'operator domain {!r}'
                            ''.format(scalar, operator.domain.field,
                                      operator.domain))

        if tmp is not None and tmp not in operator.domain:
            raise TypeError('`tmp` {!r} not an element of the '
                            'operator domain {!r}'
                            ''.format(tmp, operator.domain))

        super().__init__(operator.domain, operator.range, operator.is_linear)
        self.__operator = operator
        self.__scalar = scalar
        self.__tmp = tmp

    @property
    def operator(self):
        """The operator part of this multiplication."""
        return self.__operator

    @property
    def scalar(self):
        """The scalar part of this multiplication."""
        return self.__scalar

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``.

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorRightScalarMult(operator, 3)
        >>> left_mul_op([1, 2, 3])
        rn(3).element([3.0, 6.0, 9.0])
        """
        if out is None:
            return self.operator(self.scalar * x)
        else:
            if self.__tmp is not None:
                tmp = self.__tmp
            else:
                tmp = self.domain.element()
            tmp.lincomb(self.scalar, x)
            self.operator(tmp, out=out)

    def __mul__(self, other):
        """Implement ``self * other``.

        An optimization for repeated multiplications.
        """

        if other in self.range.field:
            return OperatorRightScalarMult(self.operator, self.scalar * other,
                                           self.__tmp)
        else:
            return super().__rmul__(other)

    @property
    def inverse(self):
        """Inverse of this operator.

        The inverse of ``op * scalar`` is given by
        ``1/scalar * op.inverse`` if ``scalar != 0``. If ``scalar == 0``,
        the inverse is not defined.

        ``OperatorRightScalarMult(op, scalar).inverse <==>``
        ``OperatorLeftScalarMult(op.inverse, 1.0/scalar)``

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorRightScalarMult(operator, 3)
        >>> left_mul_op.inverse([3, 3, 3])
        rn(3).element([1.0, 1.0, 1.0])
        """
        if self.scalar == 0.0:
            raise ZeroDivisionError('{} not invertible'.format(self))

        return (1.0 / self.scalar) * self.operator.inverse

    def derivative(self, x):
        """Return the derivative at ``x``.

        The derivative of the right scalar operator multiplication
        follows the chain rule:

        ``OperatorRightScalarMult(op, scalar).derivative(x) <==>``
        ``OperatorLeftScalarMult(op.derivative(scalar * x), scalar)``

        Parameters
        ----------
        x : `domain` `element-like`
            Evaluation point of the derivative.

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.ResidualOperator(odl.IdentityOperator(space),
        ...                                 [1, 1, 1])
        >>> left_mul_op = OperatorRightScalarMult(operator, 3)
        >>> derivative = left_mul_op.derivative([0, 0, 0])
        >>> derivative([1, 1, 1])
        rn(3).element([3.0, 3.0, 3.0])
        """
        return self.scalar * self.operator.derivative(self.scalar * x)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator scalar multiplication is the
        scalar multiplication of the operator adjoint:

        ``OperatorLeftScalarMult(op, scalar).adjoint ==``
        ``OperatorLeftScalarMult(op.adjoint, scalar)``

        Raises
        ------
        OpNotImplementedError
            If the underlying operator is non-linear.

        Examples
        --------
        >>> import odl
        >>> space = odl.rn(3)
        >>> operator = odl.IdentityOperator(space)
        >>> left_mul_op = OperatorRightScalarMult(operator, 3)
        >>> left_mul_op.adjoint([1, 2, 3])
        rn(3).element([3.0, 6.0, 9.0])
        """

        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        return self.operator.adjoint * self.scalar.conjugate()

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.operator, self.scalar)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.operator, self._scalar)


class FunctionalLeftVectorMult(Operator):

    """Expression type for the functional left vector multiplication.

    A functional is a `Operator` whose `Operator.range` is
    a `Field`. It is multiplied from left with a vector, resulting in
    an operator mapping from the `Operator.domain` to the vector's
    `LinearSpaceVector.space`.

    ``FunctionalLeftVectorMult(op, vector)(x) <==> vector * op(x)``
    """

    def __init__(self, functional, vector):
        """Initialize a new instance.

        Parameters
        ----------
        functional : `Operator`
            Functional in the vector multiplication. Its `range` must
            be a `Field`.
        vector : ``functional.range`` `element-like`
            The vector to multiply by. Its space's `LinearSpace.field` must be
            the same as ``functional.range``
        """
        if not isinstance(vector, LinearSpaceVector):
            raise TypeError('`vector` {!r} not is not a LinearSpaceVector'
                            ''.format(vector))

        if functional.range != vector.space.field:
            raise TypeError('range {!r} not is not vector.space.field {!r}'
                            ''.format(functional.range, vector.space.field))

        super().__init__(functional.domain, vector.space,
                         linear=functional.is_linear)
        self.__functional = functional
        self.__vector = vector

    @property
    def functional(self):
        """The functional part of this multiplication."""
        return self.__functional

    @property
    def vector(self):
        """The vector part of this multiplication."""
        return self.__vector

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``.

        Examples
        --------
        Create the operator ``(x * x^T)(y) = x * <x, y>``

        >>> import odl
        >>> space = odl.rn(3)
        >>> x = space.element([1, 2, 3])
        >>> functional = odl.InnerProductOperator(x)
        >>> left_mul_op = FunctionalLeftVectorMult(functional, x)
        >>> left_mul_op([1, 2, 3])
        rn(3).element([14.0, 28.0, 42.0])
        """
        if out is None:
            return self.vector * self.functional(x)
        else:
            scalar = self.functional(x)
            out.lincomb(scalar, self.vector)

    def derivative(self, x):
        """Return the derivative at ``x``.

        Left scalar multiplication and derivative are commutative:

        ``FunctionalLeftVectorMult(op, vector).derivative(x) <==>``
        ``FunctionalLeftVectorMult(op.derivative(x), vector)``

        Returns
        -------
        derivative : `FunctionalLeftVectorMult`
        """
        return FunctionalLeftVectorMult(self.functional.derivative(x),
                                        self.vector)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator scalar multiplication is the
        scalar multiplication of the operator adjoint:

        ``FunctionalLeftVectorMult(op, vector).adjoint ==
        OperatorComp(op.adjoint, vector.T)``

        ``(x * A)^T = A^T * x^T``

        Returns
        -------
        adjoint : `OperatorComp`

        Raises
        ------
        OpNotImplementedError
            If the underlying operator is non-linear.
        """

        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        return OperatorComp(self.functional.adjoint, self.vector.T)

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.functional, self.vector)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.vector, self.functional)


class OperatorLeftVectorMult(Operator):
    """Expression type for the operator left vector multiplication.

    ``OperatorLeftVectorMult(op, vector)(x) <==> vector * op(x)``

    The scalar multiplication is well-defined only if ``op.range`` is
    a ``vector.space.field``.
    """

    def __init__(self, operator, vector):
        """Initialize a new Instance.

        Parameters
        ----------
        operator : `Operator`
            The range of ``op`` must be a `LinearSpace`.
        vector : `LinearSpaceVector` in ``op.range``
            The vector to multiply by
        """
        if vector not in operator.range:
            raise TypeError('`vector` {!r} not in operator.range {!r}'
                            ''.format(vector, operator.range))

        super().__init__(operator.domain, operator.range,
                         linear=operator.is_linear)
        self.__operator = operator
        self.__vector = vector

    @property
    def operator(self):
        """The operator part of this multiplication."""
        return self.__operator

    @property
    def vector(self):
        """The vector part of this multiplication."""
        return self.__vector

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``."""
        if out is None:
            return self.operator(x) * self.vector
        else:
            self.operator(x, out=out)
            out *= self.vector

    @property
    def inverse(self):
        """Inverse of this operator.

        The inverse of ``vector * op`` is given by
        ``op.inverse / vector``.

        ``OperatorLeftVectorMult(op, vector).inverse <==>``
        ``OperatorRightVectorMult(op.inverse, 1.0/vector)``
        """

        return self.operator.inverse * (1.0 / self.vector)

    def derivative(self, x):
        """Return the derivative at ``x``.

        Left scalar multiplication and derivative are commutative:

        ``OperatorLeftVectorMult(op, vector).derivative(x) <==>``
        ``OperatorLeftVectorMult(op.derivative(x), vector)``

        See Also
        --------
        OperatorLeftVectorMult : the result
        """
        return self.vector * self.operator.derivative(x)

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator vector multiplication is the
        vector multiplication of the operator adjoint:

        ``OperatorLeftVectorMult(op, vector).adjoint ==``
        ``OperatorRightVectorMult(op.adjoint, vector)``

        ``(x * A)^T = A^T * x``

        Returns
        -------
        adjoint : `OperatorRightVectorMult`

        Raises
        ------
        OpNotImplementedError
            If the underlying operator is non-linear.
        """
        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        # TODO: handle complex vectors
        return self.operator.adjoint * self.vector

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.operator, self.vector)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.vector, self.operator)


class OperatorRightVectorMult(Operator):

    """Expression type for the operator right vector multiplication.

    ``OperatorRightVectorMult(op, vector)(x) <==> op(vector * x)``

    The scalar multiplication is well-defined only if
    ``vector in op.domain == True``.
    """

    def __init__(self, operator, vector):
        """Initialize a new `OperatorRightVectorMult` instance.

        Parameters
        ----------
        op : `Operator`
            The domain of ``op`` must be a ``vector.space``.
        vector : `LinearSpaceVector` in ``op.domain``
            The vector to multiply by
        """
        if not isinstance(operator, Operator):
            raise TypeError('`operator` {!r} not an `Operator` instance'
                            ''.format(operator))

        if vector not in operator.domain:
            raise TypeError('`vector` {!r} not in operator.domain {!r}'
                            ''.format(vector.space, operator.domain))

        super().__init__(operator.domain, operator.range,
                         linear=operator.is_linear)
        self.__operator = operator
        self.__vector = vector

    @property
    def operator(self):
        """The operator part of this multiplication."""
        return self.__operator

    @property
    def vector(self):
        """The vector part of this multiplication."""
        return self.__vector

    def _call(self, x, out=None):
        """Implement ``self(x[, out])``."""
        if out is None:
            return self.operator(x * self.vector)
        else:
            tmp = self.domain.element()
            x.multiply(self.vector, out=tmp)
            self.operator(tmp, out=out)

    @property
    def inverse(self):
        """Inverse of this operator.

        The inverse of ``op * vector`` is given by
        ``(1.0 / vector) * op.inverse``.

        ``OperatorRightVectorMult(op, vector).inverse <==>``
        ``OperatorLeftVectorMult(op.inverse, 1.0/vector)``
        """

        return (1.0 / self.vector) * self.operator.inverse

    def derivative(self, x):
        """Return the derivative at ``x``.

        Left vector multiplication and derivative are commutative:

        ``OperatorRightVectorMult(op, vector).derivative(x) <==>
        OperatorRightVectorMult(op.derivative(x), vector)``

        See Also
        --------
        OperatorRightVectorMult : the result
        """
        return self.operator.derivative(x) * self.vector

    @property
    def adjoint(self):
        """Adjoint of this operator.

        The adjoint of the operator vector multiplication is the
        vector multiplication of the operator adjoint:

        ``OperatorRightVectorMult(op, vector).adjoint ==``
        ``OperatorLeftVectorMult(op.adjoint, vector)``

        ``(A x)^T = x * A^T``

        Returns
        -------
        adjoint : `OperatorLeftVectorMult`

        Raises
        ------
        OpNotImplementedError
            If the underlying operator is non-linear.
        """
        if not self.is_linear:
            raise OpNotImplementedError('nonlinear operators have no adjoint')

        # TODO: handle complex vectors
        return self.vector * self.operator.adjoint

    def __repr__(self):
        """Return ``repr(self)``."""
        return '{}({!r}, {!r})'.format(self.__class__.__name__,
                                       self.operator, self.vector)

    def __str__(self):
        """Return ``str(self)``."""
        return '{} * {}'.format(self.operator, self.vector)


class OpTypeError(TypeError):
    """Exception for operator type errors.

    Domain errors are raised by `Operator` subclasses when trying to call
    them with input not in the domain (`Operator.domain`) or with the wrong
    range (`Operator.range`).
    """


class OpDomainError(OpTypeError):
    """Exception for domain errors.

    Domain errors are raised by `Operator` subclasses when trying to call
    them with input not in the domain (`Operator.domain`).
    """


class OpRangeError(OpTypeError):
    """Exception for domain errors.

    Domain errors are raised by `Operator` subclasses when the returned
    value does not lie in the range (`Operator.range`).
    """


class OpNotImplementedError(NotImplementedError):
    """Exception for not implemented errors in `LinearSpace`'s.

    These are raised when a method in `LinearSpace` that has not been
    defined in a specific space is called.
    """

if __name__ == '__main__':
    # pylint: disable=wrong-import-position
    from odl.util.testutils import run_doctests
    run_doctests()
