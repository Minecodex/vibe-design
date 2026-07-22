from Cython.Build import cythonize
from setuptools import Extension, setup


def build_extensions() -> list[Extension]:
    protected_modules = (
        "app.core.config",
        "app.core.license",
        "app.core.license_runtime",
        "app.core.security",
    )
    return [Extension(module_name, [module_name.replace(".", "/") + ".py"]) for module_name in protected_modules]


setup(
    name="xscz-backend-secure-build",
    ext_modules=cythonize(build_extensions(), language_level="3"),
)
