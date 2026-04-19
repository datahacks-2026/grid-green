from myorg.experimental import SuperCustomModel

model = SuperCustomModel(width=1536, depth=48)
model.train(X_train, y_train, steps=10000)
