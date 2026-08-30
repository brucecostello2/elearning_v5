import sys; sys.path.insert(0, "/app")
from app.services.scene_split import partition_narration, sentences
n = ("Hi! Today, we are going to learn how to multiply two-digit numbers. "
     "That might sound tricky, but do not worry. By the end, you will be able "
     "to solve a problem like 23 times 14 all by yourself.")
print("sentences:", sentences(n))
p = partition_narration(n)
print("is_mixed:", p.is_mixed)
print("context:", p.context_sentences)
print("digits :", p.digit_sentences)
