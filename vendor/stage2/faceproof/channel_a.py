from .index import search
def discover(embedding, config):
    result=search(embedding,config)
    for i,hit in enumerate(result["hits"][:5],1): print(f"RANK {i} score={hit['score']:.4f} author={hit.get('author_handle','')} post={hit.get('post_url','')}")
    print(f"MARGIN rank1-rank2={result['margin']:.4f} required={config.min_margin:.4f}")
    if result["hits"]: result.update({k:result["hits"][0].get(k) for k in ("post_uri","image_sha256","post_url")})
    return result
