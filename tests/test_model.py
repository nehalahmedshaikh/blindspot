import unittest

from blindspot.model import _auc, _average_precision, _fit_logistic, _predict


class ModelTests(unittest.TestCase):
    def test_auc_handles_ties_and_one_class(self):
        self.assertEqual(_auc([0, 1], [0.5, 0.5]), 0.5)
        self.assertIsNone(_auc([1, 1], [0.2, 0.8]))

    def test_logistic_model_learns_separable_signal(self):
        features = [[0.0], [0.1], [0.9], [1.0]]
        targets = [0, 0, 1, 1]
        weights = _fit_logistic(features, targets)
        predictions = [_predict(weights, row) for row in features]
        self.assertLess(predictions[0], predictions[-1])
        self.assertGreater(_average_precision(targets, predictions), 0.9)


if __name__ == "__main__":
    unittest.main()
