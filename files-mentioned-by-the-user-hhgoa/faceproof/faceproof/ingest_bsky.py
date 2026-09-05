"""Seeded public Bluesky ingestion with provenance; only configured consenting handles."""
import argparse, json
from pathlib import Path
import requests
def ingest(handles, output="data/index/raw.jsonl"):
    rows=[]
    for handle in handles:
        try:
            did=requests.get("https://public.api.bsky.app/xrpc/com.atproto.identity.resolveHandle",params={"handle":handle},timeout=15).json()["did"]
            feed=requests.get("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed",params={"actor":did,"limit":100},timeout=20).json()["feed"]
            for item in feed:
                post=item["post"]; embed=post.get("embed",{}); images=embed.get("images",[]) if embed.get("$type")=="app.bsky.embed.images#view" else []
                for image in images: rows.append({"post_uri":post["uri"],"post_url":f"https://bsky.app/profile/{handle}/post/{post['uri'].split('/')[-1]}","author_did":did,"author_handle":handle,"text":post["record"].get("text",""),"created_at":post["record"].get("createdAt",""),"image_url":image["fullsize"],"alt":image.get("alt",""),"source":"author_feed"})
        except (requests.RequestException,KeyError,ValueError) as e: print(f"INGEST {handle} failed: {e}")
    Path(output).parent.mkdir(parents=True,exist_ok=True); Path(output).write_text("".join(json.dumps(x)+"\n" for x in rows),encoding="utf-8"); print(f"INGEST records={len(rows)}"); return rows
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("--handles",nargs="+",required=True); p.add_argument("--output",default="data/index/raw.jsonl"); args=p.parse_args(); ingest(args.handles,args.output)
