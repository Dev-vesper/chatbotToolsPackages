from tools.cer_1 import PAGE_CLASS as Cer1Page
from tools.cer_2 import PAGE_CLASS as Cer2Page
from tools.cer_3 import PAGE_CLASS as Cer3Page
from ui.components import ToolPage

TOOL_PAGES: tuple[type[ToolPage], ...] = (Cer1Page, Cer2Page, Cer3Page)
