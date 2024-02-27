# Copyright 2021-2024 Avaiga Private Limited
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except in compliance with
# the License. You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.

from __future__ import annotations

import ast
import copy
import inspect
import re
import typing as t
from abc import ABC, abstractmethod
from collections.abc import Iterable
from types import FrameType

from ._context_manager import _BuilderContextManager
from ._factory import _BuilderFactory

if t.TYPE_CHECKING:
    from ..gui import Gui


class _Element(ABC):
    """NOT DOCUMENTED"""

    _ELEMENT_NAME = ""
    _DEFAULT_PROPERTY = ""
    __RE_INDEXED_PROPERTY = re.compile(r"^(.*?)__([\w\d]+)$")

    def __new__(cls, *args, **kwargs):
        obj = super(_Element, cls).__new__(cls)
        parent = _BuilderContextManager().peek()
        if parent is not None:
            parent.add(obj)
        return obj

    def __init__(self, *args, **kwargs):
        # Frame resolution to get the local variables
        source_frame = inspect.stack()[3]
        self.__locals = {
            key: value
            for key, value in t.cast(FrameType, source_frame.frame).f_locals.items()
            if not key.startswith("_")
        }
        # Manage properties
        self._properties: t.Dict[str, t.Any] = {}
        if args and self._DEFAULT_PROPERTY != "":
            self._properties = {self._DEFAULT_PROPERTY: args[0]}
        self._properties.update(kwargs)
        self._parse_properties(code_arguments=self.__get_code_arguments(source_frame))

    def __get_code_arguments(self, frame: inspect.FrameInfo):
        """
        Analyze the source code of the object creation to get the original args and kwargs
        code_arguments: {kwarg_name: kwarg_value}
        """
        code_arguments = {}
        code_context = frame.code_context or []
        for c in code_context:
            parsed_ast = ast.parse(c.strip())
            for node in ast.walk(parsed_ast):
                if isinstance(node, ast.Call):
                    if len(node.args) > 0 and self._DEFAULT_PROPERTY != "":
                        arg = node.args[0]
                        value = arg.id if isinstance(arg, ast.Name) else ast.literal_eval(arg)
                        code_arguments[self._DEFAULT_PROPERTY] = value
                    for kw in node.keywords:
                        value = kw.value.id if isinstance(kw.value, ast.Name) else ast.literal_eval(kw.value)
                        code_arguments[kw.arg] = value
        return code_arguments

    def update(self, *args, **kwargs):
        if args:
            kwargs[self._DEFAULT_PROPERTY] = args[0]
        self._properties.update(kwargs)
        update_source_frame = inspect.stack()[1]
        self._parse_properties(kwargs.keys(), self.__get_code_arguments(update_source_frame))

    # Convert property value to string
    def _parse_properties(self, updated_property_list: t.Optional[t.Iterable] = None, code_arguments: t.Dict[str, t.Any] = {}):
        updated_property_list = updated_property_list if updated_property_list is not None else self._properties.keys()
        for k in list(updated_property_list):
            v = self._properties[k]
            # Handle indexed property, remove the original key, use the new parsed key
            if k != self._parse_property_key(k):
                del self._properties[k]
                k = self._parse_property_key(k)
            self._properties[k] = self._parse_property(k, v, code_arguments)

    def _parse_property_key(self, key: str) -> str:
        if match := _Element.__RE_INDEXED_PROPERTY.match(key):
            return f"{match.group(1)}[{match.group(2)}]"
        return key

    def _parse_property(self, key: str, value: t.Any, code_arguments: t.Dict[str, t.Any]) -> t.Any:
        # Return object that has __name__ attribute (e.g. enum, class, function, etc.)
        if hasattr(value, "__name__"):
            return str(getattr(value, "__name__"))
        # Handle variable as keyword argument value
        for k, v in self.__locals.items():
            if v is value and key in code_arguments and str(code_arguments[key]).strip() == k.strip():
                return "{" + k + "}"
        # Cases that requires no modification
        if isinstance(value, (str, dict, Iterable)):
            return value
        # Default cases: stringify the value
        return str(value)

    # Get a deepcopy version of the properties
    def get_properties(self, deepcopy: bool = True) -> t.Dict[str, t.Any]:
        return copy.deepcopy(self._properties) if deepcopy else self._properties

    @abstractmethod
    def _render(self, gui: "Gui") -> str:
        pass


class _Block(_Element):
    """NOT DOCUMENTED"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._children: t.List[_Element] = []

    def add(self, *elements: _Element):
        for element in elements:
            if element not in self._children:
                self._children.append(element)
        return self

    def __enter__(self):
        _BuilderContextManager().push(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        _BuilderContextManager().pop()

    def _render(self, gui: "Gui") -> str:
        el = _BuilderFactory.create_element(gui, self._ELEMENT_NAME, self.get_properties())
        return f"{el[0]}{self._render_children(gui)}</{el[1]}>"

    def _render_children(self, gui: "Gui") -> str:
        return "\n".join([child._render(gui) for child in self._children])


class _DefaultBlock(_Block):
    _ELEMENT_NAME = "part"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class html(_Block):
    """A visual element defined as an HTML tag.

    Use this class to integrate raw HTML to your page.

    This element can be used as a block element.
    """

    def __init__(self, *args, **kwargs):
        """Create a new `html` block.

        Arguments:
            args (any[]): A list of one or two unnamed arguments:

                - *args[0]* is the HTML tag name. If empty or None, this represents an HTML text
                  node.
                - *args[1]* (optional) is the text of this element.<br/>
                  Note that special HTML characters (such as '&lt;' or '&amp;') do not need to be protected.
            kwargs (dict[str, any]): the HTML attributes for this element.<br/>
                These should be valid attribute names, with valid attribute values.

        Examples:
            - To generate `<br/>`, use:
               ```
               html("br")
               ```
            - To generate `<h1>My page title</h1>`, use:
               ```
               html("h1", "My page title")
               ```
            - To generate `<h1 id="page-title">My page title</h1>`, use:
               ```
               html("h1", "My page title", id="page-title")
               ```
            - To generate `<p>This is a <b>Taipy GUI</b> element.</p>`, use:
               ```
               with html("p"):
                   html(None, "This is a ")
                   html("b", "Taipy GUI")
                   html(None, " element.")
               ```
        """
        super().__init__(*args, **kwargs)
        if not args:
            raise RuntimeError("Can't render html element. Missing html tag name.")
        self._ELEMENT_NAME = args[0] if args[0] else None
        self._content = args[1] if len(args) > 1 else ""

    def _render(self, gui: "Gui") -> str:
        if self._ELEMENT_NAME:
            attrs = ""
            if self._properties:
                attrs = " " + " ".join([f'{k}="{str(v)}"' for k, v in self._properties.items()])
            return f"<{self._ELEMENT_NAME}{attrs}>{self._content}{self._render_children(gui)}</{self._ELEMENT_NAME}>"
        else:
            return self._content


class _Control(_Element):
    """NOT DOCUMENTED"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _render(self, gui: "Gui") -> str:
        el = _BuilderFactory.create_element(gui, self._ELEMENT_NAME, self.get_properties())
        return (
            f"<div>{el[0]}</{el[1]}></div>"
            if f"<{el[1]}" in el[0] and f"</{el[1]}" not in el[0]
            else f"<div>{el[0]}</div>"
        )

    def __enter__(self):
        raise RuntimeError(f"Can't use Context Manager for control type '{self._ELEMENT_NAME}'")

    def __exit__(self, exc_type, exc_value, traceback):
        raise RuntimeError(f"Can't use Context Manager for control type '{self._ELEMENT_NAME}'")
