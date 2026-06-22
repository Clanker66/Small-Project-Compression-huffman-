import heapq
import argparse
import struct 
import os
def build_parser():
    parser = argparse.ArgumentParser(
        prog="compressor",
        description="Compress or decompress a file using Huffman coding."
    )

    # mutually exclusive: must pick exactly one mode
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "-c", "--compress",
        action="store_true",
        help="compress the input file"
    )
    mode.add_argument(
        "-d", "--decompress",
        action="store_true",
        help="decompress the input file"
    )

    parser.add_argument(
        "input_file",
        type=str,
        help="path to the input file"
    )

    parser.add_argument(
        "-o", "--output",
        type=str,
        default=None,
        metavar="FILE",
        help="path to the output file (default: input_file with .huff added/removed)"
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="print extra information (e.g. compression ratio)"
    )

    return parser


class BST:
    def __init__(self , element , freq):
        self.freq = freq
        self.char = element
        self.left = None
        self.right = None


    def __lt__(self, other):
        if self.freq != other.freq:
            return self.freq < other.freq
        
        self_key = (1, '') if self.char == '£' else (0, self.char)
        other_key = (1, '') if other.char == '£' else (0, other.char)
        return self_key < other_key
        

def build_tree(file_name : str ):
    with open(file_name , "r") as F:
        frequencies = {}
        while True:
            contents = F.read(256)
            if not contents : 
                break
            for i in contents:
                if i in frequencies:
                    frequencies[i] += 1
                    continue
                frequencies[i] = 1
    if not frequencies:
        raise ValueError("File is empty")
                
    Tree = [] 
    for char ,freq in frequencies.items():
        Tree.append(BST(char,freq))
    heapq.heapify(Tree)
    if len(Tree) == 1:
        node = heapq.heappop(Tree)
        root = BST('£' , node.freq)
        root.left=node
        return [root]

    while len(Tree) != 1:
        left = heapq.heappop(Tree)        
        right = heapq.heappop(Tree)
        Node = BST('£' , right.freq + left.freq)
        Node.left = left
        Node.right = right
        heapq.heappush(Tree,Node)
    
    return Tree

def code_dict(root : BST , codes , cd : str = '' ):
    if not root :
        return 
    if root.char != '£':
        codes[root.char] = cd 
    code_dict(root.left , codes ,cd + '0')
    code_dict(root.right , codes , cd + '1')


def flatten(root:BST , tree , alpha ):
    if not root:
        return
    if root.char == '£':
        tree.append('0')
        flatten(root.left , tree , alpha)
        flatten(root.right , tree , alpha )
    else:
        tree.append('1')
        alpha.append(root.char)

def packing_lengths(lengths):
    packed = bytearray()
    for i in range(0,len(lengths) ,4) :
        pack = lengths[i:i+4]
        byte = 0
        for j , size in enumerate(pack):
            byte |= (size-1)<<(j*2)
        packed.append(byte)
    return bytes(packed)


def make_header(root):
    alphabet = []
    nodes = []
    flatten(root, nodes, alphabet)

    alphabet_size = len(alphabet)
    treebit = "".join(nodes)

    padding = (8 - (len(treebit) % 8)) % 8
    treebit += '0' * padding

    body = bytearray()
    body += struct.pack(">I", alphabet_size)
    body += bytearray(
        int(treebit[i:i+8], 2) for i in range(0, len(treebit), 8)
    )
    char_sizes = []
    characters = bytearray()
    for ch in alphabet:
        encoded = ch.encode("utf-8")
        char_sizes.append(len(encoded))
        characters += encoded
    
    body += packing_lengths(char_sizes)
    body += characters
    header = bytearray()
    header += struct.pack(">I", len(body)) 
    header += body

    return bytes(header)


def compress(IP: str, OP: str):
    Huff_Tree = build_tree(IP)
    codes = {}
    code_dict(Huff_Tree[0] , codes)
    with open(IP, "r") as Input:
        header = make_header(Huff_Tree[0])
        binary = bytearray(header)

        bin_chunk = ''
        body_bits = bytearray()
        while True:
            chunk = Input.read(256)
            if not chunk:
                break
            for char in chunk:
                bin_chunk += codes[char]
            full_groups = len(bin_chunk) // 8 * 8
            for j in range(0, full_groups, 8):
                body_bits.append(int(bin_chunk[j:j+8], 2))
            bin_chunk = bin_chunk[full_groups:]

        padding = (8 - len(bin_chunk) % 8) % 8
        bin_chunk += "0" * padding
        if bin_chunk:
            body_bits.append(int(bin_chunk, 2))

        binary.append(padding)     
        binary += body_bits

    with open(OP, "wb") as Output:
        Output.write(binary)

def unpacking_lengths(sizes , count):
    lengths = []

    for byte in sizes:
        for i in range(4):
            if len(lengths) >= count:
                return lengths
            size = (byte >> (2*i)) & 3
            lengths.append(size+1)
    return lengths
    

def header_parser(header, header_size):
    pointer = 0
    alphabet_size = struct.unpack_from(">I", header, pointer)[0]
    pointer += 4

    tree_bitsize = 2 if alphabet_size == 1 else (2*alphabet_size-1)
    treepadding = (8 - (tree_bitsize % 8)) % 8
    tree_start = pointer
    pointer += (treepadding + tree_bitsize)//8
    ByteTree = header[tree_start:pointer]
    bitTree = "".join(f"{b:08b}" for b in ByteTree)[:tree_bitsize]

    packed_len_count = -(-alphabet_size // 4)  
    length_bytes = header[pointer:pointer + packed_len_count]
    lengths = unpacking_lengths(length_bytes, alphabet_size)
    pointer += packed_len_count

    alphabet = []
    for i in range(alphabet_size):
        char_len = lengths[i]
        char = header[pointer:pointer+char_len].decode("utf-8")
        pointer += char_len
        alphabet.append(char)
    return (bitTree , alphabet)

    
def code_table(tree: str, alpha: list):
    tree_iter = iter(tree)
    alpha_iter = iter(alpha)
    codes = {}

    if len(alpha) == 1:
        next(tree_iter)
        next(tree_iter)
        codes[next(alpha_iter)] = '0'
        return codes

    def traverse(code):
        bit = next(tree_iter)
        if bit == '1':
            char = next(alpha_iter)
            codes[char] = code if code else '0'
        else:
            traverse(code + '0')
            traverse(code + '1')

    traverse('')
    return codes

def build_decode_table(tree: str, alpha: list):
    codes = code_table(tree, alpha)
    return {v: k for k, v in codes.items()} 

def decompress(IP: str, OP: str):
    with open(IP , "rb") as Input:
        header_chunk = Input.read(4)
        if not header_chunk:
            raise ValueError("File is empty")
        header_size = struct.unpack_from(">I" , header_chunk)[0]
        header_chunk = Input.read(header_size)
        bitTree, alpha = header_parser(header_chunk , header_size)
        chunk= Input.read()
        padding = chunk[0]
        body = chunk[1:]
        decodes = build_decode_table(bitTree , alpha)
        data_bits = "".join(f"{byte:08b}" for byte in body)
        if padding:
            data_bits = data_bits[:-padding]

        data = []
        current = ''
        for bit in data_bits:
            current += bit
            if current in decodes:
                data.append(decodes[current])
                current = ''
        contents = ''.join(data)
    with open(OP , "w") as Output:
        Output.write(contents)


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.compress:
        out_path = args.output or args.input_file.split(".")[0] + ".huff"

        if os.path.exists(out_path):
            parser.error(
                f"'{out_path}' already exists; refusing to overwrite it. "
                f"Use -o to specify a different output path."
            )

        compress(args.input_file, out_path)

        if args.verbose:
            orig_size = os.path.getsize(args.input_file)
            comp_size = os.path.getsize(out_path)
            ratio = (comp_size / orig_size) * 100 if orig_size else 0
            print(f"Compressed {args.input_file} -> {out_path}")
            print(f"{orig_size} bytes -> {comp_size} bytes ({ratio:.1f}%)")

    elif args.decompress:
        if args.output:
            out_path = args.output
        elif args.input_file.endswith(".huff"):
            out_path = args.input_file[:-5] + ".out"
        else:
            out_path = args.input_file + ".out"

        if os.path.exists(out_path):
            parser.error(
                f"'{out_path}' already exists; refusing to overwrite it. "
                f"Use -o to specify a different output path."
            )

        decompress(args.input_file, out_path)

        if args.verbose:
            print(f"Decompressed {args.input_file} -> {out_path}")


if __name__ == "__main__":
    main()