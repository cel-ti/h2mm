
from h2mm.mgr import H2MM


h2mm = H2MM.load()
h2mm.add_resource_folder("D:\\Downloads", skip_existing=True)
h2mm.reparse_resource_folder(0)
pass