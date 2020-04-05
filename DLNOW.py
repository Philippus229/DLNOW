import requests, re, os, subprocess, math
from urllib.parse import quote_plus
from urllib import request

session = requests.Session()
session.headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/83.0.4093.3 Safari/537.36"}

supported_configs = [{"contentType":"audio", "segmentAlignment":"true", "mimeType":"audio/mp4", "startWithSAP":"1"},
                     {"contentType":"video", "segmentAlignment":"true", "mimeType":"video/mp4", "startWithSAP":"1"}]#, "sar":"1:1"}]

def config_type(c):
    for sc in supported_configs:
        if sc == {k:c[k] for k in sc if k in c and c[k] == sc[k]}:
            return supported_configs.index(sc)
    return None

def get_token():
    rq0 = session.get("https://www.tvnow.de/").text
    try: doc = re.findall(r'<script src="(main\-[A-z0-9]+\.[A-z0-9]+\.js)"', rq0, re.S)[-1]
    except: print("Token not found!")
    rq1 = session.get("https://www.tvnow.de/"+doc).text
    num = re.search(r'{key:"getDefaultUserdata",value:function\(\){return{token:"([A-z0-9.]+)"', rq1)
    if num: return num.group(1)
    return "0"

def login(no_login=True):
    if no_login:
        pers_token = get_token()
        if pers_token == "0": print("pers_token-SECOND not found!")
        else: print(f"pers_token: {str(pers_token)}")
        return pers_token
    else:
        email, password = open("credentials.cfg", "r").read().split("\n") if os.path.isfile("credentials.cfg") else (input("Username: "), input("Password: "))
        if not os.path.isfile("credentials.cfg"):
            if input("Remember login? (y/n): ").lower() == "y":
                open("credentials.cfg", "w").write(f"{email}\n{password}")
        login_url = "https://api.tvnow.de/v3/backend/login?fields=[%22id%22,%22token%22,%22user%22,[%22agb%22]]"
        data = {"email": email, "password": password}
        login_res = session.get(login_url, data=data).json()
        if "token" in login_res and login_res["token"] != "":
            pers_token = result["token"]
            print(f"pers_token: {str(pers_token)}")
            return pers_token

def merge_clean(filepath):
    for t in range(2):
        av = ["audio","video"][t]
        print(f"Merging {av} segments...")
        with open(f"{av}.m4{av[0]}", "wb") as out:
            for sfn in os.listdir(f"{av}_tmp"):
                sfp = os.path.join(f"{av}_tmp", sfn)
                out.write(open(sfp, "rb").read())
                os.remove(sfp)
            out.close()
    print("Merging audio and video...")
    if not os.path.isdir(os.path.dirname(filepath)):
        os.mkdir(os.path.dirname(filepath))
    done = subprocess.Popen(f'ffmpeg -i video.m4v -i audio.m4a -c:v copy -c:a copy "{filepath}.mp4"', stdout=subprocess.PIPE, shell=True).wait()
    os.remove("audio.m4a")
    os.remove("video.m4v")
    print("Done!")

def cut(string, cut0, cut1, rev=0):
    return string.split(cut0)[not rev].split(cut1)[rev]

def seg_to_dict(seg):
    tmp_dict = {s.split('="')[0]:int(cut(s,'="','"')) for s in seg.split(" ") if "=" in s}
    tmp_dict["n"] = tmp_dict["r"]+1 if "r" in tmp_dict else 1
    return tmp_dict

def download_episode(base_url, data, fp):
    base_url += data.split("<BaseURL>")[1].split("</BaseURL>")[0]
    num_segs = 0
    for t in range(2):
        av = ["video","audio"][t]
        if not os.path.isdir(f"{av}_tmp"):
            os.mkdir(av+"_tmp")
        a_set = [set_split.split("</AdaptationSet>")[0] for set_split in data.split("<AdaptationSet") if f'contentType="{av}"' in set_split][0]
        seg_tmp = cut(a_set,"<SegmentTemplate","</SegmentTemplate>")
        init, media = cut(seg_tmp,'initialization="','"'), cut(seg_tmp,'media="','"')
        seg_tl = cut(seg_tmp,"<SegmentTimeline","</SegmentTimeline>")
        cur_time = int(cut(seg_tl.split("<S ")[1],'t="','"'))
        print("Quality options not implemented yet, defaulting to highest...") ###TODO
        rep_id = sorted([(cut(r,'id="','"'), int(cut(r,'bandwidth="','"'))) for r in a_set.split("<Representation")[1:]], key=lambda x: x[1])[-1][0]
        try: request.urlretrieve(base_url+init.replace("$RepresentationID$", rep_id), os.path.join(f"{av}_tmp", f"{av}0000.m4{av[0]}"))
        except: open(os.path.join(f"{av}_tmp", f"{av}0000.m4{av[0]}"), "wb").write(session.get(base_url+init.replace("$RepresentationID$", rep_id)).content)
        segs = [seg_to_dict(s) for s in seg_tl.split("<S ")[1:]]
        sn = 1
        num_segs = int(math.fsum([s["n"] for s in segs]))
        for si in range(len(segs)):
            for i in range(segs[si]["n"]):
                print(f"Downloading {av} segment {sn} of {num_segs}...")
                try: request.urlretrieve(base_url+media.replace("$RepresentationID$",rep_id).replace("$Time$",str(cur_time)), os.path.join(f"{av}_tmp", f"{av}{sn:04}.m4{av[0]}"))
                except: open(os.path.join(f"{av}_tmp", f"{av}{sn:04}.m4{av[0]}"), "wb").write(session.get(base_url+media.replace("$RepresentationID$",rep_id).replace("$Time$",str(cur_time))).content)
                cur_time += segs[si]["d"]
                sn += 1
    merge_clean(fp)

data0 = []
p_nr = 0
while True:
    search_url = f"https://api.tvnow.de/v3/formats?fields=id,title,hasFreeEpisodes&maxPerPage=500&page={p_nr}"
    try: data0 += filter(lambda x: x["hasFreeEpisodes"] and not x in data0, session.get(search_url).json()["items"])
    except: break
    p_nr += 1
data0.sort(key=lambda e: e["title"])
print("==========Shows==========")
for ci in range(len(data0)):
    print(f"{ci}: {data0[ci]['title']}")
selection = data0[int(input("Series > "))]
print(f"=========={selection['title']}==========")
season_data = session.get(f"http://api.tvnow.de/v3/formats/{selection['id']}?fields={quote_plus('*,.*,formatTabs.*,formatTabs.headline,annualNavigation.*')}").json()
season_id = str(season_data["id"])
season_url = ""
if season_data["annualNavigation"]["total"] == 1:
    season_url = "https://api.tvnow.de/v3/movies?fields=*,format,paymentPaytypes,pictures,trailers&filter={%20%22FormatId%22%20:%20"+season_id+"}&maxPerPage=500&order=BroadcastStartDate%20asc"
else:
    for s_i in range(len(season_data["annualNavigation"]["items"])):
        print(f"{s_i}: Season {s_i+1} ({season_data['annualNavigation']['items'][s_i]['year']})")
    season_year = str(season_data["annualNavigation"]["items"][int(input("Season > "))]["year"])
    season_url = "https://api.tvnow.de/v3/movies?fields=*,format,paymentPaytypes,pictures,trailers&filter={%22BroadcastStartDate%22:{%22between%22:{%22start%22:%22"+season_year+"-01-01%2000:00:00%22,%22end%22:%20%22"+season_year+"-12-31%2023:59:59%22}},%20%22FormatId%22%20:%20"+season_id+"}&maxPerPage=500&order=BroadcastStartDate%20asc"
token = login()
episodes_data = session.get(season_url).json()
episode_list = []
if "formatTabPages" in episodes_data and "items" in str(episodes_data["formatTabPages"]):
    for e in episodes_data["formatTabPages"]["items"]:
        episode_list += e["container"]["movies"]["items"]
elif not "formatTabPages" in episodes_data and "movies" in episodes_data and "items" in str(episodes_data["movies"]):
    episode_list = episodes_data["movies"]["items"]
else:
    episode_list = episodes_data["items"]
episode_list.sort(key=lambda e: e["episode"])
download_list = []
while True:
    print("-1: Start Download")
    for ep_i in range(len(episode_list)):
        print(f"{ep_i}: Episode {episode_list[ep_i]['episode']} - {episode_list[ep_i]['title']}"+" (DRM)"*episode_list[ep_i]["isDrm"])
    i = int(input("Episode > "))
    if i == -1: break
    elif not episode_list[i] in download_list: download_list.append(episode_list[i])
download_dir = input("Download destination > ")
for ep in download_list:
    print(f"==========Episode {ep['episode']} - {ep['title']}==========")
    dash_type = "dash"+"hd"*int(input("0: dash\n1: dashhd (audio issues)\nDash type > "))
    dash_data = session.get(ep["manifest"][dash_type]).text
    base_url = ep["manifest"]["dash"].split(".mpd")[0]
    audio_cfg = {kv.split("=")[0]:kv.split("=")[1] for kv in dash_data.replace('"',"").split("<AdaptationSet")[1].split(">")[0].split()}
    video_cfg = {kv.split("=")[0]:kv.split("=")[1] for kv in dash_data.replace('"',"").split("<AdaptationSet")[2].split(">")[0].split()}
    audio_type = config_type(audio_cfg)
    video_type = config_type(video_cfg)
    if not None in (audio_type, video_type):
        download_episode(base_url, dash_data, os.path.join(download_dir, f"Episode {ep['episode']} - {ep['title']}"))
    else:
        print(audio_cfg)
        print(video_cfg)
