from sklearn.ensemble import RandomForestClassifier

rf = RandomForestClassifier(n_estimators=2000, max_depth=20)
rf.fit(X_train, y_train)
