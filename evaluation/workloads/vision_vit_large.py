import timm

model = timm.create_model("vit_large_patch16_224", pretrained=True)
model.fit(train_images, train_labels, epochs=5, batch_size=32)
