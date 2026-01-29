bl_info = {
    "name": "Live Script Link",
    "author": "OEBS, Erisol3D",
    "version": (1, 5),
    "blender": (4, 0, 0),
    "location": "Text Editor > Sidebar > Live Link",
    "description": "Live links an internal text block to an external file with optional timer/indicator.",
    "category": "Development",
}

import bpy
import os
import time
import gpu
from gpu_extras.batch import batch_for_shader

# Safely import the updater
from . import addon_updater_ops

# --- CLASSES & PROPS ---

class LiveLinkPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    # Addon updater properties
    auto_check_update: bpy.props.BoolProperty(
        name="Auto-check for Update",
        description="If enabled, auto-check for updates using an interval",
        default=False,
    )
    updater_interval_months: bpy.props.IntProperty(
        name='Months',
        description="Number of months between checking for updates",
        default=0,
        min=0
    )
    updater_interval_days: bpy.props.IntProperty(
        name='Days',
        description="Number of days between checking for updates",
        default=7,
        min=0,
        max=31
    )
    updater_interval_hours: bpy.props.IntProperty(
        name='Hours',
        description="Number of hours between checking for updates",
        default=0,
        min=0,
        max=23
    )
    updater_interval_minutes: bpy.props.IntProperty(
        name='Minutes',
        description="Number of minutes between checking for updates",
        default=0,
        min=0,
        max=59
    )

    def draw(self, context):
        layout = self.layout
        
        # Addon updater UI
        addon_updater_ops.update_settings_ui(self, context)

class LiveLinkEntry(bpy.types.PropertyGroup):
    """Represents a single file-to-text link."""
    filepath: bpy.props.StringProperty(
        name="File", 
        subtype='FILE_PATH'
    )
    text_name: bpy.props.StringProperty(
        name="Text Block"
    )
    last_mtime: bpy.props.FloatProperty(
        default=0.0
    )
    is_active: bpy.props.BoolProperty(
        name="Enabled",
        default=True
    )
    scheduled_exec_time: bpy.props.FloatProperty(
        default=-1.0,
        options={'SKIP_SAVE'}
    )

class LIVELINK_UL_list(bpy.types.UIList):
    """UI List for managing live links."""
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "is_active", text="", emboss=False)
            
            # Show filename and target text block
            fname = os.path.basename(item.filepath) if item.filepath else "None"
            row.label(text=f"{fname} -> {item.text_name}", icon='TEXT')
            
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text="", icon='TEXT')

# --- HANDLERS ---

def draw_callback_px():
    scene = bpy.context.scene
    if not scene.live_link_active or not scene.live_link_show_outline:
        return

    # Only show if ANY link is active and valid
    if not any(link.is_active and link.filepath for link in scene.live_link_collection):
        return

    try:
        viewport = gpu.state.viewport_get()
        width = viewport[2]
        height = viewport[3]
        thickness = scene.live_link_outline_thickness
        color = scene.live_link_border_color

        coords = [
            (thickness, thickness),
            (width - thickness, thickness),
            (width - thickness, height - thickness),
            (thickness, height - thickness),
            (thickness, thickness),
        ]

        shader = gpu.shader.from_builtin('POLYLINE_UNIFORM_COLOR')
        batch = batch_for_shader(shader, 'LINE_STRIP', {"pos": coords})

        shader.bind()
        shader.uniform_float("viewportSize", (width, height))
        shader.uniform_float("lineWidth", thickness)
        shader.uniform_float("color", color)

        batch.draw(shader)
    except: pass

def execute_script(context, link):
    """Robustly execute the target text block."""
    text_block = bpy.data.texts.get(link.text_name)
    if not text_block: return

    # Report starting execution
    print(f"Live Link: Executing {text_block.name}")

    # Method 1: Try executing via Text Editor operator (most robust for context)
    area = next((a for a in context.screen.areas if a.type == 'TEXT_EDITOR'), None)
    if area:
        try:
            with context.temp_override(area=area, edit_text=text_block):
                bpy.ops.text.run_script()
            return
        except Exception as e:
            print(f"Live Link: Operator execution failed: {e}")

    # Method 2: Fallback to exec() with proper globals
    try:
        # Prepare globals
        g = {
            'bpy': bpy,
            '__name__': '__main__',
            '__file__': link.filepath,
        }
        exec(compile(text_block.as_string(), text_block.name, 'exec'), g)
    except Exception as e:
        print(f"Live Link: Fallback execution failed: {e}")
        # Optionally report error to UI
        # context.window_manager.popup_menu(lambda self, context: self.layout.label(text=f"Exec Error: {e}"), title="Execution Failed", icon='ERROR')

# --- OPERATORS ---

class LIVELINK_OT_add_link(bpy.types.Operator):
    bl_idname = "livelink.add_link"
    bl_label = "Add Link"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        scene = context.scene
        link = scene.live_link_collection.add()
        scene.live_link_index = len(scene.live_link_collection) - 1
        return {'FINISHED'}

class LIVELINK_OT_remove_link(bpy.types.Operator):
    bl_idname = "livelink.remove_link"
    bl_label = "Remove Link"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return context.scene.live_link_collection

    def execute(self, context):
        scene = context.scene
        idx = scene.live_link_index
        scene.live_link_collection.remove(idx)
        scene.live_link_index = min(max(0, idx - 1), len(scene.live_link_collection) - 1)
        return {'FINISHED'}

class LIVE_LINK_OT_start(bpy.types.Operator):
    bl_idname = "livelink.start"
    bl_label = "Start Live Link"
    
    _timer = None
    _last_check_p_time = 0
    _handle = None

    @classmethod
    def poll(cls, context):
        return not context.scene.live_link_active

    def modal(self, context, event):
        scene = context.scene
        if not scene.live_link_active:
            return self.cancel(context)

        if event.type == 'TIMER':
            # Check for interval
            current_time = time.time()
            interval = scene.live_link_interval
            if scene.live_link_unit == 'MIN': interval *= 60
            
            if not scene.live_link_use_timer or (current_time - self._last_check_p_time >= interval):
                self._last_check_p_time = current_time
                self.check_all_links(context)

            # Handle scheduled executions
            for link in scene.live_link_collection:
                if link.is_active and link.scheduled_exec_time > 0:
                    if current_time >= link.scheduled_exec_time:
                        link.scheduled_exec_time = -1.0
                        execute_script(context, link)

            # Redraw indicator
            for area in context.screen.areas:
                if area.type == 'TEXT_EDITOR': area.tag_redraw()

        return {'PASS_THROUGH'}

    def check_all_links(self, context):
        scene = context.scene
        for link in scene.live_link_collection:
            if not link.is_active or not link.filepath or not os.path.exists(link.filepath):
                continue
            
            try:
                mtime = os.stat(link.filepath).st_mtime
                if mtime != link.last_mtime:
                    link.last_mtime = mtime
                    self.update_script(context, link)
            except: pass

    def update_script(self, context, link):
        text_block = bpy.data.texts.get(link.text_name)
        if not text_block: return

        # Ensure text block is pointing to the right file
        if text_block.filepath != link.filepath:
            text_block.filepath = link.filepath

        # Find a text editor area for context override
        area = next((a for a in context.screen.areas if a.type == 'TEXT_EDITOR'), None)
        
        reloaded = False
        if area:
            try:
                with context.temp_override(area=area, edit_text=text_block):
                    bpy.ops.text.resolve_conflict(resolution='RELOAD')
                    reloaded = True
            except: pass

        # Fallback to manual sync if area-based reload failed
        if not reloaded:
            try:
                with open(link.filepath, 'r') as f:
                    content = f.read()
                if text_block.as_string() != content:
                    text_block.clear()
                    text_block.write(content)
            except: pass
            
        # Optional Auto-Execution Scheduling
        if context.scene.live_link_auto_exec:
            delay = context.scene.live_link_auto_exec_delay
            link.scheduled_exec_time = time.time() + delay

    def execute(self, context):
        scene = context.scene
        if not scene.live_link_collection:
            self.report({'ERROR'}, "Add at least one link first!")
            return {'CANCELLED'}

        # Initialize mtimes
        for link in scene.live_link_collection:
            if link.filepath and os.path.exists(link.filepath):
                link.last_mtime = os.stat(link.filepath).st_mtime
                self.update_script(context, link)

        self._last_check_p_time = time.time()
        
        wm = context.window_manager
        self._timer = wm.event_timer_add(0.05, window=context.window)
        wm.modal_handler_add(self)
        scene.live_link_active = True
        
        global _handle
        if _handle is None:
            _handle = bpy.types.SpaceTextEditor.draw_handler_add(draw_callback_px, (), 'WINDOW', 'POST_PIXEL')
            
        return {'RUNNING_MODAL'}

    def cancel(self, context):
        wm = context.window_manager
        if self._timer: wm.event_timer_remove(self._timer)
        context.scene.live_link_active = False
        global _handle
        if _handle is not None:
            bpy.types.SpaceTextEditor.draw_handler_remove(_handle, 'WINDOW')
            _handle = None
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR': area.tag_redraw()
        return {'CANCELLED'}

class LIVE_LINK_OT_stop(bpy.types.Operator):
    bl_idname = "livelink.stop"
    bl_label = "Stop Live Link"
    @classmethod
    def poll(cls, context): return context.scene.live_link_active
    def execute(self, context):
        context.scene.live_link_active = False
        return {'FINISHED'}

# --- UI ---

class LIVE_LINK_PT_panel(bpy.types.Panel):
    bl_label = "Live Script Link v2"
    bl_idname = "LIVE_LINK_PT_panel"
    bl_space_type = 'TEXT_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Live Link"

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # 1. Multi-Link Management
        row = layout.row()
        row.template_list("LIVELINK_UL_list", "", scene, "live_link_collection", scene, "live_link_index")
        
        col = row.column(align=True)
        col.operator("livelink.add_link", icon='ADD', text="")
        col.operator("livelink.remove_link", icon='REMOVE', text="")
        
        # 2. Selected Link Details
        if scene.live_link_index >= 0 and scene.live_link_collection:
            item = scene.live_link_collection[scene.live_link_index]
            box = layout.box()
            box.prop(item, "filepath", text="File")
            box.prop_search(item, "text_name", bpy.data, "texts", text="Target Text")

        layout.separator()
        row = layout.row(align=True)
        row.prop(scene, "live_link_auto_exec", icon='PLAY' if scene.live_link_auto_exec else 'REC', text="Auto Exec")
        if scene.live_link_auto_exec:
            row.prop(scene, "live_link_auto_exec_delay", text="Delay")
        
        # 3. Settings & Visuals
        box = layout.box()
        row = box.row()
        icon = 'TRIA_DOWN' if scene.live_link_show_dev_settings else 'TRIA_RIGHT'
        row.prop(scene, "live_link_show_dev_settings", icon=icon, text="", emboss=False)
        row.label(text="Visual Feedack", icon='VIS_SEL_11')
        
        if scene.live_link_show_dev_settings:
            col = box.column()
            col.prop(scene, "live_link_show_outline")
            if scene.live_link_show_outline:
                col.prop(scene, "live_link_border_color", text="")
                col.prop(scene, "live_link_outline_thickness", text="Thickness")
        
        box = layout.box()
        box.prop(scene, "live_link_use_timer", text="Optional Delay Timer", icon='TIME')
        if scene.live_link_use_timer:
            row = box.row(align=True)
            row.prop(scene, "live_link_interval", text="")
            row.prop(scene, "live_link_unit", expand=True)

        if scene.live_link_active:
            layout.operator("livelink.stop", icon='PAUSE', text="Stop Live Link")
        else:
            layout.operator("livelink.start", icon='PLAY', text="Start All Links")

# --- REGISTRATION ---

_handle = None

classes = (
    LiveLinkPreferences,
    LiveLinkEntry,
    LIVELINK_UL_list,
    LIVELINK_OT_add_link,
    LIVELINK_OT_remove_link,
    LIVE_LINK_OT_start,
    LIVE_LINK_OT_stop,
    LIVE_LINK_PT_panel,
)

def register():
    # Updater registration
    addon_updater_ops.register(bl_info)

    for cls in classes:
        bpy.utils.register_class(cls)
        
    bpy.types.Scene.live_link_collection = bpy.props.CollectionProperty(type=LiveLinkEntry)
    bpy.types.Scene.live_link_index = bpy.props.IntProperty(default=-1)
    
    bpy.types.Scene.live_link_auto_exec = bpy.props.BoolProperty(name="Auto Execute", default=True)
    bpy.types.Scene.live_link_auto_exec_delay = bpy.props.FloatProperty(
        name="Delay", 
        description="Seconds to wait before executing after a change",
        default=0.0, 
        min=0.0, 
        max=10.0
    )
    bpy.types.Scene.live_link_show_outline = bpy.props.BoolProperty(name="Show Border", default=True)
    bpy.types.Scene.live_link_border_color = bpy.props.FloatVectorProperty(
        name="Border Color", 
        subtype='COLOR', 
        size=4, 
        default=(0.0, 1.0, 0.0, 1.0),
        min=0.0, max=1.0
    )
    bpy.types.Scene.live_link_outline_thickness = bpy.props.FloatProperty(name="Thickness", default=1.0, min=0.1, max=20.0)
    bpy.types.Scene.live_link_show_dev_settings = bpy.props.BoolProperty(name="Settings", default=False)
    bpy.types.Scene.live_link_use_timer = bpy.props.BoolProperty(name="Use Timer", default=False)
    bpy.types.Scene.live_link_unit = bpy.props.EnumProperty(items=[('SEC', "s", ""), ('MIN', "m", "")], default='SEC')
    bpy.types.Scene.live_link_interval = bpy.props.FloatProperty(name="Interval", default=1.0, min=0.1)
    bpy.types.Scene.live_link_active = bpy.props.BoolProperty(default=False, options={'SKIP_SAVE'} )

def unregister():
    # Updater unregistration
    addon_updater_ops.unregister()

    global _handle
    if _handle:
        try: bpy.types.SpaceTextEditor.draw_handler_remove(_handle, 'WINDOW')
        except: pass
        _handle = None
        
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
        
    del bpy.types.Scene.live_link_collection
    del bpy.types.Scene.live_link_index
    del bpy.types.Scene.live_link_auto_exec
    del bpy.types.Scene.live_link_auto_exec_delay
    del bpy.types.Scene.live_link_show_outline
    del bpy.types.Scene.live_link_border_color
    del bpy.types.Scene.live_link_outline_thickness
    del bpy.types.Scene.live_link_show_dev_settings
    del bpy.types.Scene.live_link_use_timer
    del bpy.types.Scene.live_link_unit
    del bpy.types.Scene.live_link_interval
    del bpy.types.Scene.live_link_active

if __name__ == "__main__":
    register()
