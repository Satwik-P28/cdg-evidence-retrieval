import unittest
from bridge_probe import words, canon, bm25_scores, rank, validate


class Round25Tests(unittest.TestCase):
    def setUp(self):
        self.row = {
            'question': 'Which film was directed by the founder?',
            'context': [
                ['Founder', ['Founder directed Film B in 1990.']],
                ['Film B', ['Film B is a film.']],
                ['Film A', ['An unrelated film.']],
            ],
            'supporting_facts': [['Founder', 0], ['Film B', 0]],
            'type': 'bridge',
        }

    def test_token_unicode(self):
        self.assertEqual(words('Cécile + A_B'), ['cécile', 'a', 'b'])

    def test_normalization(self):
        self.assertEqual(canon('Film-B'), 'film b')

    def test_bm25_finite(self):
        self.assertTrue(all(x >= 0 for x in bm25_scores('film', ['film', 'film work'])))

    def test_no_prefix_match(self):
        row = dict(self.row)
        row['context'] = [['Foo', ['FooBar is nearby']], ['FooBar', ['another description']], ['Other', ['not here']]]
        self.assertNotIn('FooBar', ' ' + canon(row['context'][0][1][0]) + ' ')
        self.assertNotIn(' foo ', ' ' + canon('FooBar') + ' ')

    def test_valid_gold(self):
        validate([self.row])

    def test_invalid_gold(self):
        row = dict(self.row, supporting_facts=[['missing', 0]])
        with self.assertRaises(ValueError):
            validate([row])

    def test_valid_ranking(self):
        for method in ('bm25', 'bridge', 'mmr'):
            self.assertEqual(set(rank(self.row, method, limit=3)), {0, 1, 2})


if __name__ == '__main__':
    unittest.main()