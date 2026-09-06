# Recipe rieng cho charset_normalizer (phu thuoc an cua "requests", ma "kivy"
# keo theo qua "Kivy-Garden"). Ban build tu dong (khong qua recipe nay) hay
# bi loi vi no chon nham file .whl dung rieng cho Android trong khi buoc cai
# dat thuc te lai chay tren may Linux thuong - hai ben khong khop nen bao
# loi "is not a supported wheel on this platform".
#
# Dua no vao 1 recipe rieng nhu the nay se cai dat truc tiep tu source (pure
# Python, khong dinh gi toi file .whl dung rieng platform nao ca) nen tranh
# duoc hoan toan loi tren.
from pythonforandroid.recipe import PythonRecipe


class CharsetNormalizerRecipe(PythonRecipe):
    name = 'charset_normalizer'
    version = '3.3.2'
    url = 'https://github.com/jawah/charset_normalizer/archive/refs/tags/{version}.tar.gz'
    depends = ['setuptools']
    call_hostpython_via_targetpython = False
    site_packages_name = 'charset_normalizer'


recipe = CharsetNormalizerRecipe()
