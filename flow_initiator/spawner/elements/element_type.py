"""

   Copyright (C) Mov.ai  - All Rights Reserved
   Unauthorized copying of this file, via any medium is strictly prohibited
   Proprietary and confidential

   Developers:
   - Dor Marcous  (dor@mov.ai) - 2021
"""

from enum import Enum, auto


class ElementType(Enum):
    DYNAMIC_NODE = auto()
    PERSISTENCE_NODE = auto()
    CORE_NODE = auto()
