# (c) Copyright 2018 by Coinkite Inc. This file is part of Coldcard <coldcardwallet.com>
# and is covered by GPLv3 license found in COPYING.
#
# psbt.py - yet another PSBT parser/serializer but used only for test cases.
#
import io, struct
from binascii import b2a_hex as _b2a_hex
from .ctransaction import CTransaction
from binascii import a2b_hex
from base64 import b64decode

b2a_hex = lambda a: str(_b2a_hex(a), 'ascii')

# BIP-174 aka PSBT defined values
#
PSBT_GLOBAL_UNSIGNED_TX 	= (0)
PSBT_GLOBAL_XPUB         	= (1)

PSBT_IN_NON_WITNESS_UTXO 	= (0)
PSBT_IN_WITNESS_UTXO 	    = (1)
PSBT_IN_PARTIAL_SIG 	    = (2)
PSBT_IN_SIGHASH_TYPE 	    = (3)
PSBT_IN_REDEEM_SCRIPT 	    = (4)
PSBT_IN_WITNESS_SCRIPT 	    = (5)
PSBT_IN_BIP32_DERIVATION 	= (6)
PSBT_IN_FINAL_SCRIPTSIG 	= (7)
PSBT_IN_FINAL_SCRIPTWITNESS = (8)

PSBT_OUT_REDEEM_SCRIPT 	    = (0)
PSBT_OUT_WITNESS_SCRIPT 	= (1)
PSBT_OUT_BIP32_DERIVATION 	= (2)


# Serialization/deserialization tools
def ser_compact_size(l):
    r = b""
    if l < 253:
        r = struct.pack("B", l)
    elif l < 0x10000:
        r = struct.pack("<BH", 253, l)
    elif l < 0x100000000:
        r = struct.pack("<BI", 254, l)
    else:
        r = struct.pack("<BQ", 255, l)
    return r

def deser_compact_size(f):
    try:
        nit = f.read(1)[0]
    except IndexError:
        return None     # end of file
    
    if nit == 253:
        nit = struct.unpack("<H", f.read(2))[0]
    elif nit == 254:
        nit = struct.unpack("<I", f.read(4))[0]
    elif nit == 255:
        nit = struct.unpack("<Q", f.read(8))[0]
    return nit


class PSBTSection:

    def __init__(self, fd=None, idx=None):
        self.defaults()
        self.my_index = idx

        if not fd: return

        while 1:
            ks = deser_compact_size(fd)
            if ks is None: break
            if ks == 0: break

            key = fd.read(ks)
            vs = deser_compact_size(fd)
            val = fd.read(vs)

            kt = key[0]
            self.parse_kv(kt, key[1:], val)

    def serialize(self, fd, my_idx):

        def wr(ktype, val, key=b''):
            fd.write(ser_compact_size(1 + len(key)))
            fd.write(bytes([ktype]) + key)
            fd.write(ser_compact_size(len(val)))
            fd.write(val)

        self.serialize_kvs(wr)

        fd.write(b'\0')

class BasicPSBTInput(PSBTSection):
    def defaults(self):
        self.utxo = None
        self.witness_utxo = None
        self.part_sigs = {}
        self.sighash = None
        self.bip32_paths = {}
        self.redeem_script = None
        self.witness_script = None
        self.others = {}

    def __eq__(a, b):
        if a.sighash != b.sighash:
            if a.sighash is not None and b.sighash is not None:
                return False

        rv =  a.utxo == b.utxo and \
                a.witness_utxo == b.witness_utxo and \
                a.redeem_script == b.redeem_script and \
                a.witness_script == b.witness_script and \
                a.my_index == b.my_index and \
                a.bip32_paths == b.bip32_paths and \
                sorted(a.part_sigs.keys()) == sorted(b.part_sigs.keys())
        if rv:
            # NOTE: equality test on signatures requires parsing DER stupidness
            #       and some maybe understanding of R/S values on curve that I don't have.
            assert all(a.part_sigs[k] == b.part_sigs[k] for k in a.part_sigs)
        return rv

    def parse_kv(self, kt, key, val):
        if kt == PSBT_IN_NON_WITNESS_UTXO:
            self.utxo = val
            assert not key
        elif kt == PSBT_IN_WITNESS_UTXO:
            self.witness_utxo = val
            assert not key
        elif kt == PSBT_IN_PARTIAL_SIG:
            self.part_sigs[key] = val
        elif kt == PSBT_IN_SIGHASH_TYPE:
            assert len(val) == 4
            self.sighash = struct.unpack("<I", val)[0]
            assert not key
        elif kt == PSBT_IN_BIP32_DERIVATION:
            self.bip32_paths[key] = val
        elif kt == PSBT_IN_REDEEM_SCRIPT:
            self.redeem_script = val
            assert not key
        elif kt == PSBT_IN_WITNESS_SCRIPT:
            self.witness_script = val
            assert not key
        elif kt in ( PSBT_IN_REDEEM_SCRIPT,
                     PSBT_IN_WITNESS_SCRIPT, 
                     PSBT_IN_FINAL_SCRIPTSIG, 
                     PSBT_IN_FINAL_SCRIPTWITNESS):
            assert not key
            self.others[kt] = val
        else:
            raise KeyError(kt)

    def serialize_kvs(self, wr):
        if self.utxo:
            wr(PSBT_IN_NON_WITNESS_UTXO, self.utxo)
        if self.witness_utxo:
            wr(PSBT_IN_WITNESS_UTXO, self.witness_utxo)
        if self.redeem_script:
            wr(PSBT_IN_REDEEM_SCRIPT, self.redeem_script)
        if self.witness_script:
            wr(PSBT_IN_WITNESS_SCRIPT, self.witness_script)
        for pk, val in sorted(self.part_sigs.items()):
            wr(PSBT_IN_PARTIAL_SIG, val, pk)
        if self.sighash is not None:
            wr(PSBT_IN_SIGHASH_TYPE, struct.pack('<I', self.sighash))
        for k in self.bip32_paths:
            wr(PSBT_IN_BIP32_DERIVATION, self.bip32_paths[k], k)
        for k in self.others:
            wr(k, self.others[k])

class BasicPSBTOutput(PSBTSection):
    def defaults(self):
        self.redeem_script = None
        self.witness_script = None
        self.bip32_paths = {}

    def __eq__(a, b):
        return  a.redeem_script == b.redeem_script and \
                a.witness_script == b.witness_script and \
                a.my_index == b.my_index and \
                a.bip32_paths == b.bip32_paths

    def parse_kv(self, kt, key, val):
        if kt == PSBT_OUT_REDEEM_SCRIPT:
            self.redeem_script = val
            assert not key
        elif kt == PSBT_OUT_WITNESS_SCRIPT:
            self.witness_script = val
            assert not key
        elif kt == PSBT_OUT_BIP32_DERIVATION:
            self.bip32_paths[key] = val
        else:
            raise ValueError(kt)

    def serialize_kvs(self, wr):
        if self.redeem_script:
            wr(PSBT_OUT_REDEEM_SCRIPT, self.redeem_script)
        if self.witness_script:
            wr(PSBT_OUT_WITNESS_SCRIPT, self.witness_script)
        for k in self.bip32_paths:
            wr(PSBT_OUT_BIP32_DERIVATION, self.bip32_paths[k], k)


class BasicPSBT:
    "Just? parse and store"

    def __init__(self):

        self.txn = None
        self.xpubs = {}

        self.inputs = []
        self.outputs = []

    def __eq__(a, b):
        return a.txn == b.txn and \
            len(a.inputs) == len(b.inputs) and \
            len(a.outputs) == len(b.outputs) and \
            all(a.inputs[i] == b.inputs[i] for i in range(len(a.inputs))) and \
            all(a.outputs[i] == b.outputs[i] for i in range(len(a.outputs))) and \
            sorted(a.xpubs.items()) == sorted(b.xpubs.items())

    def parse(self, raw):
        # auto-detect and decode Base64 and Hex.
        if raw[0:10].lower() == b'70736274ff':
            raw = a2b_hex(raw.strip())
        if raw[0:6] == b'cHNidP':
            raw = b64decode(raw)
        assert raw[0:5] == b'psbt\xff', "bad magic"

        with (io.BytesIO(raw[5:]) as fd):
            
            # globals
            while 1:
                ks = deser_compact_size(fd)
                if ks is None: break

                if ks == 0: break

                key = fd.read(ks)
                vs = deser_compact_size(fd)
                val = fd.read(vs)

                kt = key[0]
                if kt == PSBT_GLOBAL_UNSIGNED_TX:
                    self.txn = val

                    t = CTransaction()
                    t.deserialize(io.BytesIO(val))
                    num_ins = len(t.vin)
                    num_outs = len(t.vout)
                elif kt == PSBT_GLOBAL_XPUB:
                    self.xpubs[key[1:]] = val
                else:
                    raise ValueError('unknown global key type: 0x%02x' % kt)

            assert self.txn, 'missing reqd section'

            self.inputs = [BasicPSBTInput(fd, idx) for idx in range(num_ins)]
            self.outputs = [BasicPSBTOutput(fd, idx) for idx in range(num_outs)]

            sep = fd.read(1)
            assert sep == b''

        return self

    def serialize(self, fd):

        def wr(ktype, val, key=b''):
            fd.write(ser_compact_size(1 + len(key)))
            fd.write(bytes([ktype]) + key)
            fd.write(ser_compact_size(len(val)))
            fd.write(val)

        fd.write(b'psbt\xff')

        wr(PSBT_GLOBAL_UNSIGNED_TX, self.txn)

        for k in self.xpubs:
            wr(PSBT_GLOBAL_XPUB, self.xpubs[k], key=k)

        # sep
        fd.write(b'\0')

        for idx, inp in enumerate(self.inputs):
            inp.serialize(fd, idx)

        for idx, outp in enumerate(self.outputs):
            outp.serialize(fd, idx)

    def as_bytes(self):
        with io.BytesIO() as fd:
            self.serialize(fd)
            return fd.getvalue()


def test_my_psbt():
    import glob, io

    for fn in glob.glob('data/*.psbt'):
        if 'missing_txn.psbt' in fn: continue
        if 'unknowns-ins.psbt' in fn: continue

        raw = open(fn, 'rb').read()
        print("\n\nFILE: %s" % fn)

        p = BasicPSBT().parse(raw)

        fd = io.BytesIO()
        p.serialize(fd)
        assert p.txn in fd.getvalue()

        chk = BasicPSBT().parse(fd.getvalue())
        assert chk == p

# EOF

