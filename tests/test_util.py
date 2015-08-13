import os
import shutil
import tempfile
import unittest

from bootstrap_salt import utils


class TestUtils(unittest.TestCase):

    def _create_src_folder_for_copytree(self, thedir):
        # Creates these files and dirs in thedir:
        #
        # folder1/
        # folder1/file1
        # folder1/folder2/
        # folder1/folder2/file2
        #
        # If we copy folder1/folder2 then folder1/ it should work.
        os.makedirs(os.path.join(thedir, "folder1", "folder2"))
        open(os.path.join(thedir, "folder1", "file1"), "w").close()
        open(os.path.join(thedir, "folder1", "folder2", "file2"), "w").close()

    def test_copytree_when_dest_already_exists(self):
        # This tests our cutsomiztion to copytree that doesn't die if the
        # target directory already eixts. Using shutil.copytree this would
        # raise an OSError

        tmp_src_folder = tempfile.mkdtemp()
        tmp_dst_folder = tempfile.mkdtemp()
        try:
            self._create_src_folder_for_copytree(tmp_src_folder)

            src1 = os.path.join(tmp_src_folder, "folder1")
            src2 = os.path.join(tmp_src_folder, "folder1", "folder2")
            dst1 = os.path.join(tmp_dst_folder, "folder1")
            dst2 = os.path.join(tmp_dst_folder, "folder1", "folder2")

            utils.copytree(src2, dst2)
            utils.copytree(src1, dst1)
        finally:
            shutil.rmtree(tmp_src_folder, ignore_errors=True)
            shutil.rmtree(tmp_dst_folder, ignore_errors=True)
