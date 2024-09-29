
input = {
    "prompt": "black forest gateau cake spelling out the words \"FLUX SCHNELL\", tasty, food photography, dynamic shot",
    "aspect_ratio" : "16:9"
} 
output = replicate.run(
    "black-forest-labs/flux-schnell",
    input=input
)
print(output)