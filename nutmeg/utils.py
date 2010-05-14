import numpy as np
import nipy.core.api as ni_api

def voxel_index_list(shape, order='ijk'):
    """From an array shape, return a list of voxel index-coordinates

    Parameters
    ----------
    shape : tuple
        the array shape
    order : str, optional
        Indicates whether the coordinate ordering should go 'ijk', or 'kji'.
        In either case, the i coordinate varies fasted,
        followed by [j, [k, [ ... ]]]

    Returns
    -------
    an ( nvox x len(shape) ) array of voxel index coordinates

    Examples
    --------
    >>> utils.voxel_index_list((2,3), order='ijk')
    array([[0, 0],
           [1, 0],
           [0, 1],
           [1, 1],
           [0, 2],
           [1, 2]])
    >>> utils.voxel_index_list((2,3), order='kji')
    array([[0, 0],
           [0, 1],
           [0, 2],
           [1, 0],
           [1, 1],
           [1, 2]])
    """
    if order=='ijk':
        arr = np.indices(shape[::-1])[::-1]
    else:
        arr = np.indices(shape)
    return np.array( [a.flatten() for a in arr] ).transpose()

def coord_list_to_mgrid(coords, shape, order='ijk'):
    """From a voxel coordinates list, make a meshgrid array

    Parameters
    ----------
    coords : np.product(shape) x ndim ndarray
        the voxel coordinate list -- MUST have coordinates for every
        point in the volume specified by shape
    shape : tuple
        the volume's shape
    order : str, optional
        Indicates whether the coordinate ordering is 'ijk', or 'kji'.
        In either case, the i coordinate varies fasted,
        followed by [j, [k, [ ... ]]]

    Returns
    -------
    a meshgrid representation of the coordinates, shaped (ndim, ni, nj, nk, ...)
    or (ndim, [...], nk, nj, ni)

    Examples
    --------
    >>> coords_list = utils.voxel_index_list((2,3), order='ijk')
    >>> coords_list
    array([[0, 0],
           [1, 0],
           [0, 1],
           [1, 1],
           [0, 2],
           [1, 2]])
    >>> mgrid = utils.coord_list_to_mgrid(coords_list, (2,3), order='ijk')
    >>> mgrid
    array([[[0, 0, 0],
            [1, 1, 1]],

           [[0, 1, 2],
            [0, 1, 2]]])
    """
    ncoords = coords.shape[0]
    if np.product(shape) != ncoords:
        raise ValueError(
"""A fully specified coordinate list must be provided"""
    )
    c_t = coords.transpose()
    if order=='ijk':
        return np.array( [a.reshape(shape[::-1]).transpose() for a in c_t] )
    else:
        return np.array( [a.reshape(shape) for a in c_t] )

def parameterize_cmap(coordmap):
    dt = [('incoord', object), ('outcoord', object), ('affine', object)]
    a = np.zeros(1, dtype=dt)
    a['incoord'][0] = coordmap.input_coords.coord_names
    a['outcoord'][0] = coordmap.output_coords.coord_names
    a['affine'][0] = coordmap.affine
    return a

def cmap_from_array(arr):
    return ni_api.Affine.from_params(arr['incoord'][0],
                                     arr['outcoord'][0],
                                     arr['affine'][0].astype('f'))

class array_pickler_mixin(object):
    """
    Can save-itself-as/load-itself-from a funky structured array.

    The structure is VERY brittle.

    This is accomplished by requiring each class that inherits this
    functionality to conform to the following rules:

    * define two class-level fields:
        _argnames -- the list of names of positional arguments
                     in the constructor
        _kwnames  -- the list of names of keyword arguments in
                     the constructor
    * The positional arguments must be listed in the correct order.
    * The names in both lists must be attributes of the class objects.
    * Each name in the kwnames list must be identical to both the
      corresponding class object attribute AND the keyword argument
      name in the class constructor.
    * All attributes named in the lists must be of type:
      * ndarray
      * array_pickler_mixin subclass
      * any type that can be reconstructed such that
        a == type(a) (asarray(a) )
        (satisfied by most built-in types)

    Examples
    --------
    >>> class A(array_pickler_mixin):
    ...     _argnames = ['str', 'arr']
    ...     def __init__(self, a_string, an_array):
    ...         self.str = a_string
    ...         self.arr = an_array
    >>> class B(array_pickler_mixin):
    ...     _argnames = ['arr', 'atype']
    ...     # these need to also be identical to the name keyword args
    ...     _kwnames = ['opt1', 'opt2']
    ...     def __init__(self, an_array, typeA, opt1=None, opt2=None):
    ...         self.arr = an_array
    ...         self.atype = typeA
    ...         self.opt1 = opt1
    ...         self.opt2 = opt2
    >>> a = A('asdf', np.random.randn(10))
    >>> b = B(np.arange(20), a)
    >>> b.save('bsave') # actually, this don't work on the command-line
    >>> b2 = B.load('bsave.npy')
    """
    
    _argnames = []
    _kwnames = []

    @classmethod
    def _get_dtype(klass):
        type_list = [(n, object) for n in klass._argnames+klass._kwnames]
        type_list.append( ('conversion_lookup', object) )
        return np.dtype(type_list)

    def save(self, f):
        np.save(f, np.asarray(self))

    def __array__(self):
        a = np.empty(1, dtype=self._get_dtype())
        names = self._argnames + self._kwnames
        conversion_lookup = dict()
        for n in names:
            attr = getattr(self, n, None)
            # name rule for obj->array converter is "_array_from_"+n
            arr_composer = '_array_from_'+n
            obj_composer = '_reconstruct_'+n
            
            # handle special array conversion rule first
            if hasattr(self, arr_composer) and hasattr(self, obj_composer):
                conversion_lookup[n] = obj_composer
                a[n][0] = getattr(self, arr_composer)(attr)
                continue

            # in recovering this element, do
            # nothing if either None, or ndarray
            if attr is None or issubclass(type(attr), np.ndarray):
                conversion_lookup[n] = None
            else:
                conversion_lookup[n] = type(attr)
            # this reads weird.. basically avoid doing asarray(None) here
            a[n][0] = np.asarray(attr) if attr is not None else None
        a['conversion_lookup'][0] = conversion_lookup
        return a

    @classmethod
    def load(klass, f):
        try:
            arr = np.load(f)
            return klass.from_array(arr)
        except AttributeError:
            return klass.from_array(f)

    @classmethod
    def from_array(klass, a, **kwargs):
        if a.dtype != klass._get_dtype():
            raise ValueError('dtype of input array does not match')

        converters = dict(a['conversion_lookup'][0])

        def convert(tp, arr_obj):
            if tp is None:
##                 print 'not converting', arr_obj
                return arr_obj
            # handle special converter rule first
            if issubclass(type(tp), str):
                converter = getattr(klass, tp)
                return converter(arr_obj)
            if issubclass(tp, array_pickler_mixin):
##                 print 'converting to array_pickler_mixin', arr_obj
                return tp.from_array(arr_obj)
##             print 'converting to some type:', tp, arr_obj
            return tp(arr_obj)

        args = (convert(converters[n], a[n][0]) for n in klass._argnames)
        kws = dict( ((n, convert(converters[n], a[n][0]))
                     for n in klass._kwnames) )
        
        # this way, the user-defined keywords take precedence of whatever is
        # found (or not found) in the record array
        kws.update(kwargs)
        return klass(*args, **kws)
