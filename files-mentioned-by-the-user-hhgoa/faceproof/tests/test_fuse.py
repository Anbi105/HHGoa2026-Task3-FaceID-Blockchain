from faceproof.fuse import fuse
def test_corroborated(): assert fuse({"accepted":True,"post_uri":"x"},{"accepted":True,"post_uri":"x"})["outcome"] == "CORROBORATED"
def test_single(): assert fuse({"accepted":True},{"accepted":False})["outcome"] == "SINGLE_CHANNEL_A"
def test_abstain(): assert fuse({"accepted":False},{"accepted":False})["outcome"] == "ABSTAIN"
