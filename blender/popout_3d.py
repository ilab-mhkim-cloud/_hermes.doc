"""
입체(팝아웃) 착시 영상 생성 스크립트 — Blender 4.x / 5.x

원리: 카메라 앞 일정 거리에 '액자 테두리 + 흰색 가로 띠'를 놓고,
물체가 그 띠보다 카메라 쪽으로 튀어나오면서 띠를 가리면
화면 밖으로 튀어나오는 것처럼 보이는 착시가 생긴다.

실행:
  blender -b -P popout_3d.py -- --out ./out/frame_ --frames 96 --samples 24
  (또는 pip install bpy 후: python popout_3d.py -- ...)
결과 PNG 시퀀스 -> ffmpeg 로 mp4 변환:
  ffmpeg -framerate 24 -i out/frame_%04d.png -c:v libx264 -pix_fmt yuv420p popout.mp4
"""
import bpy, math, sys, argparse
from mathutils import Vector

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser()
ap.add_argument("--out", default="//out/frame_")
ap.add_argument("--frames", type=int, default=96)
ap.add_argument("--samples", type=int, default=24)
ap.add_argument("--res", type=int, default=540)       # 가로 해상도 (세로 = 16/9배)
ap.add_argument("--save-blend", default="")
args = ap.parse_args(argv)

# ---------- 초기화 ----------
bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene
scn.frame_start, scn.frame_end = 1, args.frames
scn.render.fps = 24
scn.render.resolution_x = args.res
scn.render.resolution_y = int(args.res * 16 / 9)
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = args.samples
scn.cycles.use_denoising = True
scn.render.filepath = args.out
scn.render.image_settings.file_format = "PNG"
scn.view_settings.view_transform = "Standard"  # 흰 띠가 완전한 흰색이 되도록

world = bpy.data.worlds.new("W"); scn.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0

def mat(name, color, emission=False, metal=0.0, rough=0.4):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if emission:
        sh = nt.nodes.new("ShaderNodeEmission")
        sh.inputs["Color"].default_value = (*color, 1); sh.inputs["Strength"].default_value = 1.0
    else:
        sh = nt.nodes.new("ShaderNodeBsdfPrincipled")
        sh.inputs["Base Color"].default_value = (*color, 1)
        sh.inputs["Metallic"].default_value = metal
        sh.inputs["Roughness"].default_value = rough
    nt.links.new(sh.outputs[0], out.inputs["Surface"])
    return m

M_WHITE = mat("BarWhite", (1, 1, 1), emission=True)
M_BLACK = mat("FrameBlack", (0, 0, 0), emission=True)
M_FLOOR = mat("Floor", (0.08, 0.09, 0.12), rough=0.25)
M_WALL  = mat("Wall", (0.15, 0.17, 0.25), rough=0.8)
M_RED   = mat("Ball", (0.9, 0.05, 0.03), rough=0.15)
M_GOLD  = mat("Gold", (1.0, 0.7, 0.2), metal=1.0, rough=0.2)
M_CYAN  = mat("Cyan", (0.0, 0.7, 0.9), rough=0.3)

def box(name, loc, size, m):
    bpy.ops.mesh.primitive_cube_add(location=loc)
    o = bpy.context.active_object; o.name = name
    o.scale = (size[0] / 2, size[1] / 2, size[2] / 2)
    o.data.materials.append(m)
    return o

# ---------- 카메라 ----------
CAM_Y = -10.0
bpy.ops.object.camera_add(location=(0, CAM_Y, 0), rotation=(math.radians(90), 0, 0))
cam = bpy.context.active_object; scn.camera = cam
cam.data.lens = 50; cam.data.sensor_fit = "VERTICAL"; cam.data.sensor_height = 36

# ---------- 착시 레이어: 액자 + 흰 띠 (카메라에서 D 만큼 앞) ----------
D = 4.0
FY = CAM_Y + D
vis_h = D * 36 / 50              # 해당 거리에서 화면 세로 크기
vis_w = vis_h * 9 / 16
T = 0.05 * vis_w                 # 테두리 두께
# 바깥 흰 여백 + 검은 액자선 (화면 가장자리)
for nm, loc, sz, m in [
    ("FrameL", (-vis_w/2 + T/2, FY, 0), (T, 0.01, vis_h), M_WHITE),
    ("FrameR", ( vis_w/2 - T/2, FY, 0), (T, 0.01, vis_h), M_WHITE),
    ("FrameT", (0, FY,  vis_h/2 - T/2), (vis_w, 0.01, T), M_WHITE),
    ("FrameB", (0, FY, -vis_h/2 + T/2), (vis_w, 0.01, T), M_WHITE),
]:
    box(nm, loc, sz, m)
lt = T * 0.15
for nm, loc, sz in [
    ("LineL", (-vis_w/2 + T, FY + 0.01, 0), (lt, 0.01, vis_h - 2*T)),
    ("LineR", ( vis_w/2 - T, FY + 0.01, 0), (lt, 0.01, vis_h - 2*T)),
    ("LineT", (0, FY + 0.01,  vis_h/2 - T), (vis_w - 2*T, 0.01, lt)),
    ("LineB", (0, FY + 0.01, -vis_h/2 + T), (vis_w - 2*T, 0.01, lt)),
]:
    box(nm, loc, sz, M_BLACK)
# 가로 흰 띠 2개 — 착시의 핵심
BAR = 0.035 * vis_h
for i, z in enumerate((vis_h * 0.2, -vis_h * 0.2)):
    box(f"Bar{i}", (0, FY, z), (vis_w, 0.01, BAR), M_WHITE)

# ---------- 배경 무대 ----------
box("Floor", (0, 10, -2.2), (40, 40, 0.2), M_FLOOR)
box("BackWall", (0, 14, 6), (40, 0.2, 16), M_WALL)
for x in (-3, 3):
    box(f"Pillar{x}", (x, 8, 2), (0.6, 0.6, 8), M_WALL)

bpy.ops.object.light_add(type="AREA", location=(3, -4, 6))
key = bpy.context.active_object; key.data.energy = 1500; key.data.size = 4
key.rotation_euler = (math.radians(50), 0, math.radians(25))
bpy.ops.object.light_add(type="AREA", location=(-4, 6, 4))
rim = bpy.context.active_object; rim.data.energy = 800; rim.data.size = 3
rim.data.color = (0.4, 0.7, 1.0)
rim.rotation_euler = (math.radians(-60), 0, math.radians(-30))

# ---------- 주인공: 튕기며 튀어나오는 공 ----------
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.9, segments=64, ring_count=32, location=(0, 10, 0))
ball = bpy.context.active_object; ball.name = "Ball"
bpy.ops.object.shade_smooth(); ball.data.materials.append(M_RED)

N = args.frames
def ease(t): return t * t * (3 - 2 * t)
for f in range(1, N + 1):
    t = (f - 1) / (N - 1)
    y = 10 + (CAM_Y + 3.0 - 10) * ease(t)        # 멀리서 카메라 바로 앞까지
    bounce = abs(math.sin(t * math.pi * 3.0)) * 2.2 * (1 - t) + 0.4 * t
    ball.location = (0.25 * math.sin(t * math.pi), y, -1.3 + bounce)
    ball.rotation_euler = (-t * 14, 0, t * 2)
    ball.keyframe_insert("location", frame=f)
    ball.keyframe_insert("rotation_euler", frame=f)

# 공을 따라 날아오는 작은 큐브들 (일부는 띠를 넘어 튀어나옴)
import random; random.seed(7)
for i in range(14):
    m = M_GOLD if i % 2 else M_CYAN
    c = box(f"Chip{i}", (0, 0, 0), (0.25, 0.25, 0.25), m)
    start = random.uniform(0.15, 0.6)
    ang = random.uniform(0, 2 * math.pi)
    spread = random.uniform(0.4, 1.1)
    spin = Vector((random.uniform(-8, 8), random.uniform(-8, 8), random.uniform(-8, 8)))
    for f in range(1, N + 1):
        t = (f - 1) / (N - 1)
        k = max(0.0, (t - start) / (1 - start))
        y = 9 + (CAM_Y + 1.6 - 9) * k
        r = spread * k * 1.6
        c.location = (math.cos(ang) * r, y, 0.2 + math.sin(ang) * r)
        c.rotation_euler = spin * t
        c.hide_render = (k == 0.0)
        c.keyframe_insert("location", frame=f)
        c.keyframe_insert("rotation_euler", frame=f)
        c.keyframe_insert("hide_render", frame=f)

if args.save_blend:
    bpy.ops.wm.save_as_mainfile(filepath=args.save_blend)
bpy.ops.render.render(animation=True)
