import xgboost as xgb

model = xgb.XGBClassifier(n_estimators=500, max_depth=10, learning_rate=0.05)
model.fit(X_train, y_train)
