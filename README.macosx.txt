This package requires Python 2.7. One way to get this is to install
Homebrew <http://mxcl.github.com/homebrew/> and hence Python 2.7.

Then to create an environment compatible with Texturepacker you do
this::

    /usr/local/Cellar/python/2.7.1/bin/virtualenv --distribute \
        --no-site-packages NAME

where NAME is the name of the new virtual environment (a directory with
this name will be created). Then do

    NAME/bin/activate

Now when you use pip to install the packages, the changes all happen in
this copy of Python; your regular Python install will not be affected.
