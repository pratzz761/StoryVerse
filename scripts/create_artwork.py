"""Rebuild StoryVerse's original SVG sample covers. No AI or external assets."""
from pathlib import Path
import random

OUTPUT = Path(__file__).resolve().parent.parent / "frontend" / "public" / "covers"
OUTPUT.mkdir(parents=True, exist_ok=True)
random.seed(14)


def write(name, title, content):
    noise = '<filter id="paper"><feTurbulence type="fractalNoise" baseFrequency=".65" numOctaves="3" stitchTiles="stitch"/><feColorMatrix type="saturate" values="0"/><feComponentTransfer><feFuncA type="linear" slope=".085"/></feComponentTransfer><feBlend in="SourceGraphic" mode="soft-light"/></filter>'
    OUTPUT.joinpath(name + ".svg").write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 600" role="img"><title>{title} — original sample illustration</title><defs>{noise}</defs><g filter="url(#paper)">{content}</g></svg>', encoding="utf-8")


def stars(color, count, bottom=400):
    return ''.join(f'<circle cx="{random.randint(20,880)}" cy="{random.randint(20,bottom)}" r="{random.choice([.7,1,1.3,1.8])}" fill="{color}" opacity="{random.uniform(.3,.8):.2f}"/>' for _ in range(count))


def pine(x, y, scale, color):
    return f'<g transform="translate({x} {y}) scale({scale})" fill="{color}"><path d="M0 0 29 85 17 80 42 125 28 120 53 164 35 157 61 201H8V239H-8V201H-61L-35 157-53 164-28 120-42 125-17 80-29 85Z"/></g>'


forest = '<defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="#718b78"/><stop offset="1" stop-color="#c6c59a"/></linearGradient><linearGradient id="water" x2="0" y2="1"><stop stop-color="#b5bea0"/><stop offset="1" stop-color="#6c9b92"/></linearGradient></defs><path fill="url(#sky)" d="M0 0h900v600H0z"/>'
forest += '<circle cx="550" cy="175" r="73" fill="#dddbaf" opacity=".8"/><path d="m0 355 158-171 88 80 135-142 115 150 105-83 199 170v241H0" fill="#738a73" opacity=".7"/><path d="m0 405 150-94 117 65 121-99 171 113 137-61 204 80v191H0" fill="#536f62"/>'
for layer, color, count, s, lo, hi in [(0,'#5e7b68',20,.8,180,280),(1,'#3d6256',14,1.1,210,320),(2,'#254b42',12,1.45,160,280)]:
    for i in range(count):
        x=i*900/count+random.randint(-20,20)
        if 390<x<650 and layer==2: continue
        forest += pine(x,random.randint(lo,hi),s,color)
forest += '<path d="M510 375q-75 50 0 86t-96 139h300q-225-95-150-146t-12-79" fill="url(#water)"/><path d="M0 477q202-67 439-12l-90 135H0Z" fill="#193f37"/><path d="M900 421q-172-24-324 53l134 126h190Z" fill="#22463b"/><path d="M376 446q130-62 254-24l-1 14q-133-27-252 26Z" fill="#917b54"/><path d="M375 445q130-63 257-24M381 439l-2-29m38 14v-30m38 17v-28m39 19v-29m38 24v-30m39 26v-29m38 29v-25" fill="none" stroke="#b09c6b" stroke-width="4"/>'
forest += '<g transform="translate(531 386)"><circle cx="0" cy="0" r="7" fill="#e4c6a1"/><path d="m-5 8-11 28 30 1-11-29Z" fill="#bd7650"/><path d="m-4 36-3 21m12-21 5 19" stroke="#263c35" stroke-width="5"/><path d="m-8 12-12 14" stroke="#d6b088" stroke-width="4"/><path d="m-22 13-5 41" stroke="#bca477" stroke-width="2"/></g>'
for x,y,s in [(0,40,2.4),(105,-40,2.4),(850,-35,2.7),(920,80,2.5)]: forest += pine(x,y,s,'#12392f')
forest += '<path d="M0 0h900v32Q783 73 698 30q-112 61-209 8Q338 92 247 29 128 85 0 49Z" fill="#173d30"/>'
for _ in range(24): forest += f'<circle cx="{random.randint(300,730)}" cy="{random.randint(190,520)}" r="1.7" fill="#e2c67c" opacity=".8"/>'
write('forest','The Forest That Remembers',forest)

space = '<defs><linearGradient id="space" x2=".8" y2="1"><stop stop-color="#1d253d"/><stop offset="1" stop-color="#6d5873"/></linearGradient><linearGradient id="planet" x2="1" y2="1"><stop stop-color="#d3b2a6"/><stop offset=".5" stop-color="#a38e9f"/><stop offset="1" stop-color="#585b7c"/></linearGradient></defs><path fill="url(#space)" d="M0 0h900v600H0z"/>' + stars('#ece2c8',110)
space += '<circle cx="600" cy="210" r="149" fill="#d2bdad" opacity=".06"/><circle cx="600" cy="210" r="126" fill="url(#planet)"/><path d="M502 139q84-60 196 8m-213 44q132-68 232 17m-232 35q127-15 215 34" fill="none" stroke="#dbc0af" stroke-width="16" opacity=".2"/><ellipse cx="600" cy="220" rx="229" ry="30" transform="rotate(-24 600 220)" stroke="#c6b1a7" stroke-width="15" fill="none" opacity=".6"/><path d="M0 507 80 422l87 63 82-28 100 75 108-65 91 23 99-49 103 65 150-50v144H0Z" fill="#333849"/><path d="m0 548 108-30 114 34 96-22 137 42 122-61 81 33 107-20 135 45v31H0Z" fill="#202a37"/>'
space += '<g transform="translate(405 458)"><path d="m0-15 40-18 71 32-60 15-51-6Z" fill="#d8c5b0"/><path d="m40-33 12 47 21-8-10-30Z" fill="#7d7782"/><path d="m13-20 11-15 16 2-7 7Z" fill="#a6bbbd"/><path d="m-2-11-37 6 39 5" fill="#c9856a"/><path d="m10 8-9 18m73-18 12 18" stroke="#9d9c9c" stroke-width="4"/></g><path d="m684 458 1-31m-8 10h15m-8-15a6 6 0 1 0 0-12 6 6 0 0 0 0 12" stroke="#e1c2a5" stroke-width="5" fill="none"/>'
write('space','Somewhere Beyond Tomorrow',space)

city = '<defs><linearGradient id="dusk" x2="0" y2="1"><stop stop-color="#645572"/><stop offset="1" stop-color="#d69885"/></linearGradient><linearGradient id="street" x2="0" y2="1"><stop stop-color="#6b565e"/><stop offset="1" stop-color="#282e41"/></linearGradient></defs><path fill="url(#dusk)" d="M0 0h900v600H0z"/><circle cx="585" cy="160" r="58" fill="#eac4a0" opacity=".8"/>'
city += '<path d="m0 350 167-124 81 41 147-72 151 74 141-92 213 140v283H0" fill="#726575"/><path fill="url(#street)" d="M250 340h400l250 260H0Z"/>'
for x,y,w,h in [(0,170,180,370),(170,240,130,235),(300,285,90,130),(720,125,180,430),(610,208,110,260),(545,275,70,140)]:
    city += f'<path d="M{x} {y}h{w}v{h}H{x}Z" fill="#37394a"/><path d="m{x-13} {y} {w/2+13}-35 {w/2+13} 35-8 12H{x-5}Z" fill="#282d40"/>'
    for k in range(2):
        wy=y+37+k*66
        city+=f'<path d="M{x+18} {wy}h{w-36}v30H{x+18}Z" fill="#b98a76" opacity=".75"/><path d="M{x+18} {wy+15}h{w-36}m{-int((w-36)/2)}-15v30" stroke="#4f414d" stroke-width="4"/>'
city += '<path d="m105 208 689-51M257 293l474-65" stroke="#353448" fill="none" stroke-width="3"/><path d="M351 300v190m-14-162h59m300-140v352m-18-315h63" fill="none" stroke="#303043" stroke-width="6"/>'
for x,y in [(122,265),(270,325),(642,289),(757,222),(380,355)]: city+=f'<path d="M{x} {y-30}v25" stroke="#292e40" stroke-width="3"/><ellipse cx="{x}" cy="{y}" rx="15" ry="23" fill="#dfac83"/><path d="M{x-9} {y-15}q-6 15 0 30m18-30q6 15 0 30" stroke="#bd816b" fill="none" stroke-width="1.5"/>'
city += '<path d="m448 600 22-157m43 157-18-157m-309 84 206-99m313 99-208-99" stroke="#d2a18b" opacity=".25" stroke-width="3"/><g transform="translate(480 395)"><ellipse cy="0" rx="6" ry="7" fill="#e9bf9b"/><path d="m-5 7-8 31h25L5 7" fill="#ca9d88"/><path d="m-5 30-4 23m13-23 4 22" stroke="#333346" stroke-width="5"/></g>'
write('city','The Last Light in Kyoto',city)

ocean = '<defs><linearGradient id="seaSky" x2="0" y2="1"><stop stop-color="#527b8c"/><stop offset="1" stop-color="#d2cbb2"/></linearGradient><linearGradient id="sea" x2="0" y2="1"><stop stop-color="#688e92"/><stop offset="1" stop-color="#1b4e64"/></linearGradient></defs><path fill="url(#seaSky)" d="M0 0h900v600H0z"/><circle cx="640" cy="160" r="63" fill="#e0d9b8"/><path d="M0 330h900v270H0Z" fill="url(#sea)"/><path d="m0 340 150-100 96 60 118-26 127 71Z" fill="#718b8a"/><path d="M0 440q129-36 280 2t310-12 310 16m-900 58q140-42 280 0t310-12 310 16m-900 63q140-42 280 0t310-12 310 16" fill="none" stroke="#9bb3a9" opacity=".45" stroke-width="4"/>'
ocean += '<path d="M0 600V385q73-26 147 19l117 55-24 141Z" fill="#2b514c"/><path d="m0 438 124-16 69 30-42 65-151 34Z" fill="#547469"/><path d="M514 408h161l-30 25H542Z" fill="#4b4a43"/><path d="M588 407V241l-66 147h61Z" fill="#e2d6b4"/><path d="m596 277 61 110h-61Z" fill="#c8c8ad"/><path d="m596 242 32 11-32 10Z" fill="#b47e65"/><path d="m520 452 60-3m16-4h58m-26 16h-76" stroke="#c0c9b4" stroke-width="2" opacity=".6"/><path d="m126 388 1-41m-8 11h16m-9-14a6 6 0 1 0 0-12 6 6 0 0 0 0 12m18 48v-34m-6 8h12m-6-12a5 5 0 1 0 0-10 5 5 0 0 0 0 10" stroke="#ddc8a0" stroke-width="4" fill="none"/><path d="m220 168 12-4 12 4m75-26 10-4 10 4m373 73 10-4 10 4" stroke="#4e6d76" fill="none" stroke-width="2"/>'
write('ocean','Where the Ocean Ends',ocean)

moon = '<defs><linearGradient id="night" x2="0" y2="1"><stop stop-color="#353653"/><stop offset="1" stop-color="#9f8396"/></linearGradient></defs><path fill="url(#night)" d="M0 0h900v600H0z"/>' + stars('#e4d9c3',100)
moon += '<circle cx="583" cy="188" r="104" fill="#e3d6bd"/><circle cx="552" cy="153" r="19" fill="#c7bfb0" opacity=".5"/><circle cx="616" cy="218" r="26" fill="#c7bfb0" opacity=".5"/><circle cx="625" cy="152" r="9" fill="#c7bfb0" opacity=".4"/><path d="M0 439 80 375h46v-46h45v90h51v-51h83v-53h37v129h62v-38h90v-62h44v86h38v-59h90v-57h49v102h68v-47h72v-62h40v62h70v169H0Z" fill="#49455d"/><path d="M0 475h97v-41h62v41h37v-77h74v99h66v-46h94v-39h52v77h63v-33h39v-55h82v78h60v-51h113v67h61v105H0Z" fill="#302e48"/>'
moon += '<path d="M0 509h900v91H0Z" fill="#22283b"/><path d="M0 504h900v9H0Z" fill="#524758"/><path d="M650 506v-95h7v95m-7-93h90v94h-7v-88h-76" fill="#302b3f"/><path d="M675 454h44v31h-44Z" fill="#d3ba97"/><path d="m675 454 22 16 22-16" fill="none" stroke="#a48e7d" stroke-width="2"/><g transform="translate(416 467)"><circle cy="-13" r="9" fill="#c9a58c"/><path d="m-8-4-7 38h29L8-4" fill="#b78889"/><path d="m-7 31-5 35m17-35 8 35" stroke="#322e43" stroke-width="7"/><path d="m8 6 20 12 9-7" stroke="#c9a58c" stroke-width="5"/></g><path d="m201 188 38 8-31 12 8 26-38-8 12-13Z" fill="#d9d0b9" transform="rotate(-15 211 211)"/>'
write('moon','Letters from the Moon',moon)

desert = '<defs><linearGradient id="desertSky" x2="0" y2="1"><stop stop-color="#a27977"/><stop offset="1" stop-color="#e1bd8e"/></linearGradient></defs><path fill="url(#desertSky)" d="M0 0h900v600H0z"/><circle cx="570" cy="163" r="82" fill="#eed7a6"/><path d="M0 373q191-100 383 0t517-30v257H0Z" fill="#c09770"/><path d="M0 465q233-142 453-18t447-30v183H0Z" fill="#a87859"/>'
desert += '<g fill="#806957"><path d="M496 342V199l28-31 28 31v143Z"/><path d="M481 220h87v14h-87Zm-59 141V265h51v96Zm155 0V243h51v118Z"/><path d="M520 176v-57h7v57Zm-91 89v-26h39v26Zm158-22v-24h32v24Z"/></g><path d="M508 339V215h31v124Z" fill="#5f5a4b"/><path d="M516 240v-14h15v14Zm0 36v-14h15v14Zm0 36v-14h15v14Z" fill="#d7b77c"/><path d="M404 364h242l-30 14H426Z" fill="#b69a74"/><path d="M0 555q183-70 368-64t532 48v61H0Z" fill="#835b49"/><path d="M0 582q190-50 403-18t497 14v22H0Z" fill="#634b42"/><path d="m486 383-54 161h-69l97-161Z" fill="#d1b184"/><path d="m437 532-62 1m68-18-60 1m66-18-55 1m61-17-51 1m55-17-44 1m50-18-41 1m47-18-37 1m41-15-31 1m36-14-29 1" stroke="#936b50" stroke-width="3"/>'
desert += '<g transform="translate(385 515)"><circle cy="-16" r="6" fill="#d8b88c"/><path d="m-5-10-10 27h28L5-10Z" fill="#4e5e5a"/><path d="m-4 16-6 18m14-18 7 18" stroke="#493e38" stroke-width="5"/><path d="m13-8 8 41" stroke="#b89a71" stroke-width="2"/></g><path d="m90 133 24-4m603 91 21-3m-518 35 30-4" stroke="#d4ad87" stroke-width="2"/>'
write('desert','The City Beneath the Sand',desert)
print(f"Wrote 6 original sample covers to {OUTPUT}")
