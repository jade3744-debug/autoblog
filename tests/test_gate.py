import copy
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from gate import digest, check_review, check_publish

class GateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bundle = Path(self.temp.name)
        (self.bundle / 'post.md').write_text('검토할 원고', encoding='utf-8')
        (self.bundle / 'image.png').write_bytes(b'image-fixture')
        self.review = {'model':'gpt-6.1-sol', 'reasoning':'medium', 'verdict':'PASS',
                       'artifact_sha256':digest(self.bundle), 'blockers':[],
                       'scores':dict.fromkeys(('intent','accuracy','originality','readability','images'), 90)}
        self.approval = {'approved':True, 'approved_by':'user-1',
                         'approved_at':'2026-01-01T00:00:00+00:00',
                         'artifact_sha256':digest(self.bundle)}
    def test_valid(self):
        self.assertEqual(check_publish(self.bundle,self.review,self.approval),digest(self.bundle))
    def test_no_user_approval(self):
        self.approval['approved']=False
        with self.assertRaisesRegex(ValueError,'USER_APPROVAL_REQUIRED'):
            check_publish(self.bundle,self.review,self.approval)
    def test_text_edit_invalidates_review(self):
        (self.bundle/'post.md').write_text('변경')
        with self.assertRaisesRegex(ValueError,'REVIEW_CONTENT_CHANGED'):
            check_publish(self.bundle,self.review,self.approval)
    def test_image_edit_invalidates_review(self):
        (self.bundle/'image.png').write_bytes(b'new image')
        with self.assertRaisesRegex(ValueError,'REVIEW_CONTENT_CHANGED'):
            check_review(self.bundle,self.review)
    def test_re_review_still_requires_new_approval(self):
        (self.bundle/'post.md').write_text('수정 및 재검수')
        self.review['artifact_sha256']=digest(self.bundle)
        with self.assertRaisesRegex(ValueError,'APPROVAL_CONTENT_CHANGED'):
            check_publish(self.bundle,self.review,self.approval)
    def test_reject_model_fallback(self):
        self.review['model']='gpt-6-luna'
        with self.assertRaisesRegex(ValueError,'REVIEW_MODEL_MISMATCH'):
            check_review(self.bundle,self.review)
    def test_quality_failures(self):
        for field,value in [('blockers',['unverified fact']),('scores',dict.fromkeys(self.review['scores'],80))]:
            review=copy.deepcopy(self.review); review[field]=value
            with self.assertRaises(ValueError): check_review(self.bundle,review)
    def test_reject_invalid_scores(self):
        for value in [True,float('nan'),float('inf'),101,-1,'90']:
            review=copy.deepcopy(self.review); review['scores']['accuracy']=value
            with self.assertRaisesRegex(ValueError,'INVALID_SCORE_VALUE'):
                check_review(self.bundle,review)
    def test_file_removal_invalidates(self):
        (self.bundle/'image.png').unlink()
        with self.assertRaisesRegex(ValueError,'REVIEW_CONTENT_CHANGED'):
            check_review(self.bundle,self.review)
    def test_symlink_rejected(self):
        (self.bundle/'alias').symlink_to(self.bundle/'post.md')
        with self.assertRaisesRegex(ValueError,'SYMLINK_NOT_ALLOWED'): digest(self.bundle)
    def test_invalid_time(self):
        self.approval['approved_at']='2099-01-01T00:00:00+00:00'
        with self.assertRaisesRegex(ValueError,'INVALID_APPROVAL_TIME'):
            check_publish(self.bundle,self.review,self.approval)

if __name__ == '__main__': unittest.main()
