import heapq
import argparse
import struct 
import os

def lz77_matching(data  , max_window = 1<<12 , min_match = 3 , max_match = 255):
    tokens =[]
    n = len(data)
    i = 0

    while i < n:
        best_dist = 0
        best_len = 0
        window_start = max(0 , i-max_window)

        for j in range(window_start , i):

            length = 0
            while(i+length<n and data[j+length] == data[i+length] and  length<max_match):
                length += 1
            if length > best_len:
                best_len = length
                best_dist = i-j

        if best_len >= min_match:
            tokens.append((1,best_dist,best_len))
            i += best_len
        else :
            tokens.append((0,data[i]))
            i+=1
    return tokens


def lz77_encode(tokens):
    data = bytearray()

    for token in tokens:
        if token[0] : 
            data.append(token[0])
            data += token[1].to_bytes(2,"big")
            data.append(token[2])
        else:
            data.append(token[0])
            data.append(token[1])
    return bytes(data)

def lz77_decode(data):
    tokens = []
    pointer = 0
    n = len(data)
    while pointer < n:
        flag = data[pointer]
        pointer +=1
        if flag:
            dist = int.from_bytes(data[pointer:pointer+2] , "big")
            length = data[pointer+2]
            pointer += 3
            tokens.append((flag , dist , length))
        else:
            tokens.append((flag , data[pointer]))
            pointer +=1
    return tokens


def huffman_to_lz77(huffman_data):
    tokens = lz77_decode(huffman_data)
    data = []
    for token in tokens:
        chunk = []
        if token[0] :
            n = len(data) 
            dist = token[1]
            for i in range(token[2]):
                data.append(data[n-dist+i])
            data += chunk
        else :
            data.append(token[1])
    return bytes(data)



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
        
        self_key = (1, '') if self.char == -1 else (0, self.char)
        other_key = (1, '') if other.char == -1 else (0, other.char)
        return self_key < other_key
        

def build_tree(data):
    frequencies = {}
    for byte in data:
        if byte not in frequencies:
            frequencies[byte] = 0
        frequencies[byte] += 1
                
    Tree = [] 
    for char ,freq in frequencies.items():
        Tree.append(BST(char,freq))
    heapq.heapify(Tree)
    if len(Tree) == 1:
        node = heapq.heappop(Tree)
        root = BST(-1 , node.freq)
        root.left=node
        return [root]

    while len(Tree) != 1:
        left = heapq.heappop(Tree)        
        right = heapq.heappop(Tree)
        Node = BST(-1 , right.freq + left.freq)
        Node.left = left
        Node.right = right
        heapq.heappush(Tree,Node)
    
    return Tree

def code_dict(root : BST , codes , cd : str = '' ):
    if not root :
        return 
    if root.char != -1:
        codes[root.char] = cd 
    code_dict(root.left , codes ,cd + '0')
    code_dict(root.right , codes , cd + '1')


def flatten(root:BST , tree , alpha ):
    if not root:
        return
    if root.char == -1:
        tree.append('0')
        flatten(root.left , tree , alpha)
        flatten(root.right , tree , alpha )
    else:
        tree.append('1')
        alpha.append(root.char)

def make_header(root):
    # header = [alphabet size][tree bits][alphabet bytes]
    alphabet = []
    nodes = []
    flatten(root, nodes, alphabet)

    alphabet_size = len(alphabet)
    treebit = "".join(nodes)

    padding = (8 - (len(treebit) % 8)) % 8
    treebit += '0' * padding

    body = bytearray()
    body.append(alphabet_size-1)
    body += bytearray(
        int(treebit[i:i+8], 2) for i in range(0, len(treebit), 8)
    )

    for ch in alphabet:
        body.append(ch)
    
    return bytes(body)


def lz77_to_huffman(lz77_data):
    Huff_Tree = build_tree(lz77_data)
    codes = {}
    code_dict(Huff_Tree[0] , codes)
    header = make_header(Huff_Tree[0])
    binary = bytearray(header)
    body = []
    for char in lz77_data:
        body += codes[char]
    padding = (8 - len(body) % 8) % 8
    body += "0" * padding
    binary.append(padding)
    body = ''.join(body)
    body_bits = bytearray()
    for i in range(0,len(body),8):
        body_bits.append(int(body[i:i+8],2))    
    print(body_bits) 
    binary += body_bits

    return bytes(binary)

def compress(IP : str , OP :str):
    with open(IP , "rb") as Input:
        data = Input.read()
        tokens = lz77_matching(data ,min_match=5)
        lz77_bytes = lz77_encode(tokens)
        data_bytes = lz77_to_huffman(lz77_bytes)
    
    with open(OP , "wb") as Ouput:
        Ouput.write(data_bytes)


def header_parser(header):
    pointer = 0
    alphabet_size = header[pointer] +1
    pointer += 1

    tree_bitsize = 2 if alphabet_size == 1 else (2*alphabet_size-1)
    treepadding = (8 - (tree_bitsize % 8)) % 8
    tree_start = pointer
    pointer += (treepadding + tree_bitsize)//8
    ByteTree = header[tree_start:pointer]
    bitTree = "".join(f"{b:08b}" for b in ByteTree)[:tree_bitsize]

    alphabet = []
    for _ in range(alphabet_size):
        char = header[pointer]
        pointer += 1
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

def decompress(IP: str , OP :str):
    with open(IP , "rb") as Input:
        byte = Input.read(1)
        if not byte:
            raise ValueError("File is empty")
        alpha_size = int.from_bytes(byte)+1
        Input.seek(0)
        tree_size = 2 if alpha_size == 1 else 2*alpha_size-1
        header_size = alpha_size + -(-(tree_size)//8)
        header_chunk = Input.read(header_size+1)
        bitTree, alpha = header_parser(header_chunk)
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
    content = huffman_to_lz77(bytes(data))
    with open(OP,"bw") as Output:
        Output.write(content)





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