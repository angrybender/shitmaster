import pprint
import re

class PatchError(Exception):
    pass


def apply_patch(source_code, patch):
    source_code = [(re.sub(r'[\s+]', '', line), line) for line in source_code.split("\n")]

    # struct of patch block
    patch_blocks = []
    patch_blocks_heap = []
    for line in patch.split("\n"):
        if line.rstrip() == '<<<<<<< SEARCH':
            if patch_blocks_heap:
                patch_blocks.append(patch_blocks_heap)
                patch_blocks_heap = []

            patch_blocks_heap.append(line)
        elif line.rstrip() == '>>>>>>> REPLACE':
            patch_blocks.append(patch_blocks_heap)
            patch_blocks_heap = []
        else:
            patch_blocks_heap.append(line)

    if patch_blocks_heap:
        patch_blocks.append(patch_blocks_heap)
    patch_blocks = [_[1:] for _ in patch_blocks if [__ for __ in _ if __]]

    if not patch_blocks:
        raise PatchError("bad patch [1]")

    # search replacing lines
    last_code_line_search_i = 0
    replace_blocks = []
    for i, patch_block in enumerate(patch_blocks):
        try:
            divitor = patch_block.index('=======')
        except:
            raise PatchError(f"bad patch block [1:{i}]")

        search = patch_block[:divitor]
        if not search:
            raise PatchError(f"bad patch block [2:{i}]")

        search = [re.sub(r'[\s+]', '', line) for line in search]

        _search_hash = " ".join(search)
        for source_i in range(last_code_line_search_i, len(source_code)):
            hash, _ = source_code[source_i]
            if hash != search[0]:
                continue

            _source_hash = [_[0] for _ in source_code[source_i:source_i + len(search)]]
            if " ".join(_source_hash) == _search_hash:
                last_code_line_search_i = source_i + 1
                replace_blocks.append((source_i, len(search), patch_block[divitor + 1:]))

    if not replace_blocks:
        raise PatchError("bad patch [2]")

    # apply patch:
    source_code_tree = []
    for line in source_code:
        source_code_tree.append([line[1]])

    for start_i, source_cnt, patch_lines in replace_blocks:
        last_offset_source = -1
        for i, patch_line in enumerate(patch_lines):
            if i < source_cnt:
                source_code_tree[start_i + i] = [patch_line]
                last_offset_source = start_i + i
            else:
                source_code_tree[last_offset_source].append(patch_line)

        if len(patch_lines) < source_cnt:
            last_offset_source = max(last_offset_source-1, start_i)
            for i in range(last_offset_source, last_offset_source+source_cnt):
                source_code_tree[i] = None

    source_code_tree = [_ for _ in source_code_tree if _ is not None]
    return "\n".join(
        ["\n".join(block) for block in source_code_tree]
    )