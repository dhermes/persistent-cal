from os.path import abspath
from os.path import dirname
from os.path import join
import subprocess


curr_dir = dirname(abspath(__file__))
git_hooks_dir = abspath(join(curr_dir, '../.git/hooks'))

hook_files = ['pre-commit', 'post-commit']
for hook_file in hook_files:
  cmd = ['ln', '-s', join(curr_dir, hook_file), join(git_hooks_dir, hook_file)]
  subprocess.Popen(cmd)
