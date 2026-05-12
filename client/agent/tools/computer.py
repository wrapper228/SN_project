import asyncio
import base64
import math
import os
import time
import io
import pyperclip
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict, cast, get_args
from uuid import uuid4

import pyautogui
import mss
import mss.tools
from PIL import Image
from anthropic.types.beta import BetaToolComputerUse20241022Param, BetaToolUnionParam

from .base import BaseAnthropicTool, ToolError, ToolResult

# PyAutoGUI failsafe - move mouse to corner to abort
pyautogui.FAILSAFE = True

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

Action_20241022 = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]

Action_20250124 = (
    Action_20241022
    | Literal[
        "left_mouse_down",
        "left_mouse_up",
        "scroll",
        "hold_key",
        "wait",
        "triple_click",
    ]
)

Action_20251124 = Action_20250124 | Literal["zoom"]

ScrollDirection = Literal["up", "down", "left", "right"]

class Resolution(TypedDict):
    width: int
    height: int

MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "XGA": Resolution(width=1024, height=768),  # 4:3
    "WXGA": Resolution(width=1280, height=800),  # 16:10
    "FWXGA": Resolution(width=1366, height=768),  # ~16:9
}

class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"

class ComputerToolOptions(TypedDict, total=False):
    display_height_px: int
    display_width_px: int
    display_number: int | None

def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]

class ComputerTool(BaseAnthropicTool):
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of the local computer.
    """
    name: Literal["computer"] = "computer"
    api_type: Literal["computer_20241022", "computer_20250124"] = "computer_20250124"
    
    _screenshot_delay = 1.0
    _scaling_enabled = True

    def __init__(self):
        super().__init__()
        # Get actual screen size
        self.width, self.height = pyautogui.size()
        self.display_num = None # Single display assumption for now on Windows

    @property
    def options(self) -> ComputerToolOptions:
        width, height = self.scale_coordinates(
            ScalingSource.COMPUTER, self.width, self.height
        )
        options = {
            "display_width_px": width,
            "display_height_px": height,
        }
        if self.display_num is not None:
             options["display_number"] = self.display_num
        return options

    def to_params(self) -> BetaToolUnionParam:
        return cast(
            BetaToolUnionParam,
            {"name": self.name, "type": self.api_type, **self.options},
        )

    async def __call__(
        self,
        *,
        action: Action_20250124,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        start_coordinate: tuple[int, int] | None = None,
        scroll_direction: ScrollDirection | None = None,
        scroll_amount: int | None = None,
        duration: int | float | None = None,
        key: str | None = None,
        **kwargs,
    ):
        if action in ("mouse_move", "left_click_drag"):
            if coordinate is None:
                raise ToolError(f"coordinate is required for {action}")
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")

            if action == "left_click_drag":
                if start_coordinate is None:
                    # In pyautogui we might not need start if we move there first, but let's follow spec
                    pass
                # Move to start, drag to end
                # Need to implement drag
                x, y = self.validate_and_get_coordinates(coordinate)
                # If start_coordinate is provided, move there first
                if start_coordinate:
                    start_x, start_y = self.validate_and_get_coordinates(start_coordinate)
                    pyautogui.moveTo(start_x, start_y)
                
                pyautogui.dragTo(x, y, button='left')
                return await self.screenshot()
            
            elif action == "mouse_move":
                x, y = self.validate_and_get_coordinates(coordinate)
                pyautogui.moveTo(x, y)
                return await self.screenshot()

        if action in ("key", "type"):
            if text is None:
                raise ToolError(f"text is required for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")

            if action == "key":
                # Handle key combos with improved reliability
                # Mapping Anthropic keys to PyAutoGUI
                normalized_key = self._map_keys(text)
                keys = normalized_key.split('+')
                
                # CRITICAL FIX: Add delay for focus/stability (like Shift+Insert)
                # This dramatically improves hotkey reliability on Windows
                await asyncio.sleep(0.5)
                
                # Use keyDown/keyUp instead of hotkey() for better reliability
                # This gives Windows time to process each key press properly
                try:
                    # Press all modifier keys (ctrl, shift, alt, win, etc)
                    for key in keys[:-1]:  # All except the last key
                        pyautogui.keyDown(key)
                        await asyncio.sleep(0.05)  # Small delay between key presses
                    
                    # Press and release the final key
                    pyautogui.press(keys[-1])
                    await asyncio.sleep(0.05)
                    
                    # Release all modifier keys in reverse order
                    for key in reversed(keys[:-1]):
                        pyautogui.keyUp(key)
                        await asyncio.sleep(0.05)
                        
                except Exception as e:
                    # If anything fails, ensure all modifier keys are released
                    for key in keys[:-1]:
                        try:
                            pyautogui.keyUp(key)
                        except:
                            pass
                    raise ToolError(f"Hotkey execution failed: {e}")
                
                return await self.screenshot()
            
            elif action == "type":
                # Use clipboard for typing to avoid encoding/layout issues
                pyperclip.copy(text)
                # Small delay to ensure clipboard is updated
                await asyncio.sleep(1.0) 
                pyautogui.hotkey('shift', 'insert')
                return await self.screenshot()

        if action in (
            "left_click",
            "right_click",
            "double_click",
            "triple_click",
            "middle_click",
            "screenshot",
            "cursor_position",
        ):
            if action == "screenshot":
                return await self.screenshot()
            
            elif action == "cursor_position":
                x, y = pyautogui.position()
                scaled_x, scaled_y = self.scale_coordinates(ScalingSource.COMPUTER, x, y)
                return ToolResult(output=f"X={scaled_x},Y={scaled_y}")
            
            else:
                # Clicks
                if coordinate:
                    x, y = self.validate_and_get_coordinates(coordinate)
                    pyautogui.moveTo(x, y)
                
                click_map = {
                    "left_click": {"button": "left", "clicks": 1},
                    "right_click": {"button": "right", "clicks": 1},
                    "middle_click": {"button": "middle", "clicks": 1},
                    "double_click": {"button": "left", "clicks": 2},
                    "triple_click": {"button": "left", "clicks": 3},
                }
                params = click_map[action]
                pyautogui.click(**params)
                return await self.screenshot()

        if action == "scroll":
             if scroll_direction is None:
                 raise ToolError("scroll_direction required")
             if scroll_amount is None:
                 raise ToolError("scroll_amount required")
             
             # PyAutoGUI scroll is platform dependent.
             # On Windows, positive is up.
             # scroll_amount in clicks.
             clicks = scroll_amount * 100 # Multiplier might need tuning
             
             if coordinate:
                 x, y = self.validate_and_get_coordinates(coordinate)
                 pyautogui.moveTo(x, y)

             if scroll_direction == "up":
                 pyautogui.scroll(clicks)
             elif scroll_direction == "down":
                 pyautogui.scroll(-clicks)
             elif scroll_direction in ("left", "right"):
                 # Horizontal scroll
                 h_clicks = clicks if scroll_direction == "right" else -clicks
                 pyautogui.hscroll(h_clicks)
                 
             return await self.screenshot()

        if action == "wait":
             await asyncio.sleep(duration or 1.0)
             return await self.screenshot()

        raise ToolError(f"Invalid action: {action}")

    def validate_and_get_coordinates(self, coordinate: tuple[int, int] | None = None):
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) != 2:
            raise ToolError(f"{coordinate} must be a tuple of length 2")
        if not all(isinstance(i, int) and i >= 0 for i in coordinate):
            raise ToolError(f"{coordinate} must be a tuple of non-negative ints")

        return self.scale_coordinates(ScalingSource.API, coordinate[0], coordinate[1])

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        """Scale coordinates to a target maximum resolution."""
        if not self._scaling_enabled:
            return x, y
        
        ratio = self.width / self.height
        target_dimension = None
        
        for dimension in MAX_SCALING_TARGETS.values():
            if abs(dimension["width"] / dimension["height"] - ratio) < 0.02:
                if dimension["width"] < self.width:
                    target_dimension = dimension
                break
                
        if target_dimension is None:
            return x, y
            
        x_scaling_factor = target_dimension["width"] / self.width
        y_scaling_factor = target_dimension["height"] / self.height
        
        if source == ScalingSource.API:
            if x > target_dimension["width"] or y > target_dimension["height"]:
                # Loose check
                pass
            # scale up from API (small) to Screen (big)
            return round(x / x_scaling_factor), round(y / y_scaling_factor)
        
        # scale down from Screen (big) to API (small)
        return round(x * x_scaling_factor), round(y * y_scaling_factor)

    async def screenshot(self):
        """Take a screenshot, resize if needed, return base64."""
        # Wait for UI to settle before taking screenshot (User Request #3)
        await asyncio.sleep(3.0)

        output_dir = Path("outputs")
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"screenshot_{uuid4().hex}.png"

        # Capture with MSS
        with mss.mss() as sct:
            monitor = sct.monitors[1] # Primary monitor
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
        
        # Scale if needed
        if self._scaling_enabled:
            target_w, target_h = self.scale_coordinates(ScalingSource.COMPUTER, self.width, self.height)
            img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Check size optimization
        # 1. Try saving as optimized PNG
        buffer = io.BytesIO()
        img.save(buffer, format="PNG", optimize=True)
        size_bytes = buffer.tell()
        
        if size_bytes > 4_500_000: # If > 4.5MB (limit is 5MB)
            # Try to resize to 70% first, keeping PNG
            new_w, new_h = int(img.width * 0.7), int(img.height * 0.7)
            img_resized = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            buffer = io.BytesIO()
            img_resized.save(buffer, format="PNG", optimize=True)
            size_bytes = buffer.tell()
            
            if size_bytes > 4_500_000:
                # If still too big, then go to JPEG with high quality
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=95) # High quality JPEG
                
                if buffer.tell() > 4_500_000:
                     # Last resort: lower quality JPEG
                     buffer = io.BytesIO()
                     img.save(buffer, format="JPEG", quality=85)
            
        # Write to file for debug/logging
        with open(path, "wb") as f:
            f.write(buffer.getvalue())
            
        if path.exists():
            # Determine format based on magic bytes or just track it
            is_jpeg = buffer.getvalue().startswith(b'\xff\xd8')
            media_type = "image/jpeg" if is_jpeg else "image/png"
            
            return ToolResult(
                base64_image=base64.b64encode(buffer.getvalue()).decode(),
                image_media_type=media_type
            )
        raise ToolError("Failed to take screenshot")

    def _map_keys(self, text: str) -> str:
        """Map Anthropic key names to PyAutoGUI key names."""
        # Common differences
        map_dict = {
            "Return": "enter",
            "Super": "win",
            "Command": "win", # Approximate
            "Escape": "esc",
        }
        # Handle combinations like "ctrl+Return"
        parts = text.split('+')
        mapped_parts = [map_dict.get(p, p.lower()) for p in parts]
        return '+'.join(mapped_parts)
